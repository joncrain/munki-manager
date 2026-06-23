import base64
import json
import plistlib
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import structlog
import yaml
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from automunki.api.deps import get_session
from automunki.api.routes.icons import IconUploadResponse
from automunki.core.config import settings
from automunki.core.db import async_session_factory
from automunki.core.security import current_optional_user
from automunki.models.autopkg import (
    ApprovalStatus,
    AutoPkgMetadataCacheEntry,
    AutoPkgRecipe,
    AutoPkgRun,
    AutoPkgRunResult,
    AutoPkgSchedule,
    GitHubRecipe,
    GitHubRecipeRepo,
    RecipeResultStatus,
    RunStatus,
    RunTriggerType,
    TrustChangeRequest,
    TrustStatus,
)
from automunki.models.munki import (
    PKGINFO_METADATA_RECIPE_IDENTIFIER_KEY,
    Catalog,
    PkgInfo,
    PkgInfoCatalog,
    WorkflowPreferences,
)
from automunki.models.user import User
from automunki.schemas.autopkg import (
    ApprovalRequest,
    AutoPkgRecipeCreate,
    AutoPkgRecipeImportOverrideRequest,
    AutoPkgRecipeRead,
    AutoPkgRecipeUpdate,
    AutoPkgRunRead,
    AutoPkgScheduleCreate,
    AutoPkgScheduleRead,
    AutoPkgScheduleUpdate,
    GitHubCustomRepoAdd,
    GitHubRecipeRepoRead,
    GitHubRunContextUpdate,
    MetadataCacheRead,
    MetadataCacheWrite,
    PkgInfoIngest,
    RecipeTrustSummaryResponse,
    RunResultCreate,
    RunResultRead,
    TriggerRunRequest,
    TrustApprovalRequest,
    TrustChangeRequestRead,
    TrustCommitResolveRequest,
    TrustCommitResolveResponse,
    TrustPendingCountResponse,
    VerifyTrustForRunRecipeResult,
    VerifyTrustForRunRequest,
    VerifyTrustForRunResponse,
)
from automunki.schemas.common import PaginatedResponse
from automunki.services.audit import create_audit_entry
from automunki.services.autopkg import (
    add_custom_repo_to_cache,
    discover_recipes_in_repo,
    normalize_github_full_name,
    remove_github_repo_from_cache,
    sync_all_recipes_to_cache,
    sync_repo_recipes_to_cache,
    sync_repos_to_cache,
)
from automunki.services.autopkg_metadata_cache import (
    expand_cache_entry,
    normalize_cache_entry,
)
from automunki.services.autopkg_runs import (
    autopkg_run_to_read,
    create_and_dispatch_autopkg_run,
    ensure_recipe_names_runnable,
    list_recipes_for_run,
    normalize_runner_type,
    verify_trust_live_for_recipes,
)
from automunki.services.autopkg_schedule import (
    assert_valid_cron_expression,
    assert_valid_timezone,
    fire_due_schedules,
    schedule_next_for_row,
)
from automunki.services.promotion import run_all_auto_promotions
from automunki.services.recipe_input_merge import (
    merged_recipe_input,
    substitute_input_vars,
)
from automunki.services.shard_rollout import maybe_init_shard_after_catalog_change
from automunki.services.storage import (
    StorageNotConfiguredError,
    get_storage_backend,
    sanitize_relative_path,
)
from automunki.services.trust import (
    GitHubForbiddenError,
    GitHubRateLimitError,
    build_location_cache,
    build_override_data,
    compute_trust_info,
    fetch_recipe_content,
    infer_repos_from_trust_info,
    merge_db_trust_into_plist_for_runner,
    persist_verify_trust_result,
    resolve_introducing_commit,
    trust_info_from_plist_parent_recipe_trust,
    verify_trust,
)
from automunki.services.ui_icons import store_icon

logger = structlog.get_logger()


def _strip_pkginfo_from_input(input_dict: dict | None) -> dict | None:
    """Return a copy of Input without ``pkginfo`` (canonical pkginfo lives in override plist only)."""
    if not input_dict or "pkginfo" not in input_dict:
        return input_dict
    rest = {k: v for k, v in input_dict.items() if k != "pkginfo"}
    return rest if rest else None


def _normalize_pkginfo_into_override_only(recipe: AutoPkgRecipe) -> None:
    """
    When ``override_data`` is set, ``pkginfo`` must live only under ``override_data.Input``,
    not duplicated in ``input_variables``.
    """
    if not recipe.override_data:
        return
    iv = recipe.input_variables
    if not isinstance(iv, dict) or "pkginfo" not in iv:
        return
    pkg = iv["pkginfo"]
    rest = {k: v for k, v in iv.items() if k != "pkginfo"}
    recipe.input_variables = rest if rest else None
    od = dict(recipe.override_data)
    inp = dict(od.get("Input") or {})
    inp["pkginfo"] = pkg
    od["Input"] = inp
    recipe.override_data = od


def _apply_extract_icon_to_runner_plist(recipe: AutoPkgRecipe, plist: dict) -> None:
    """When the recipe has ``extract_icon_enabled``, set ``Input.extract_icon`` for MunkiImporter."""
    if not recipe.extract_icon_enabled:
        return
    inp = plist.get("Input")
    if not isinstance(inp, dict):
        inp = {}
        plist["Input"] = inp
    inp["extract_icon"] = True


_UPPER_INPUT_KEY = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def _coerce_input_scalars_to_str(inp: dict) -> dict:
    """Coerce non-string ``Input`` scalars to strings for the runner plist.

    AutoPkg's wiki documents the convention that ``UPPER_CASE`` Input keys
    are string variables consumed via ``%VAR%`` substitution, while
    ``lower_case`` keys carry native types (bools like ``extract_icon``,
    dicts like ``pkginfo``, lists like ``catalogs``). JSON storage and JS
    form parsers (notably the override editor's ``kvToDict``, which runs
    ``JSON.parse`` on every entry) can promote a bare numeric value like
    ``"5"`` to a JSON ``int`` and a bare ``"true"`` to a JSON ``bool``.
    ``plistlib.dump`` then writes ``<integer>5</integer>`` or ``<true/>``
    in the override, and AutoPkg's ``do_variable_substitution``
    (``RE_KEYREF.sub(getdata, item)``) crashes the moment that variable is
    referenced inside a string template:

    * ``re_pattern = "(?s)(Blender(%MAJOR_VERSION%\\.\\d+)/)..."`` in
      ``Blender.download.recipe`` →
      ``TypeError: sequence item 1: expected str instance, int found``.
    * ``derive_minimum_os_version = "%DERIVE_MIN_OS%"`` in
      ``Cursor.munki.recipe`` →
      ``TypeError: sequence item 0: expected str instance, bool found``.

    Strategy: for top-level Input keys whose name matches the AutoPkg
    upper-case substitution convention, coerce ``int``/``float``/``bool``
    to their string form. Lower-case keys (``extract_icon``,
    ``unattended_install``, …), dicts, lists, and ``None`` are left alone.
    ``bool`` is a subclass of ``int`` so it is checked first.
    """
    out: dict = {}
    for k, v in inp.items():
        if v is None or isinstance(v, (dict, list)):
            out[k] = v
            continue
        is_substitution_key = isinstance(k, str) and bool(_UPPER_INPUT_KEY.match(k))
        if isinstance(v, bool):
            out[k] = ("true" if v else "false") if is_substitution_key else v
        elif isinstance(v, (int, float)):
            out[k] = str(v) if is_substitution_key else v
        else:
            out[k] = v
    return out


def _runner_plist_dict_for_recipe(recipe: AutoPkgRecipe) -> dict:
    """
    Build the override plist dict passed to AutoPkg runners (same shape as
    ``overrides[].plist`` in ``GET /autopkg/runs/config``).
    """
    if recipe.override_data:
        plist = dict(recipe.override_data)
        trust = plist.get("ParentRecipeTrustInfo") or {}
        trust.setdefault("parent_recipes", {})
        trust.setdefault("non_core_processors", {})
        if trust:
            plist["ParentRecipeTrustInfo"] = trust
        merge_db_trust_into_plist_for_runner(plist, recipe.trust_info)
        # Single effective Input for the runner: merge loose ``input_variables`` with plist Input.
        merged_in = merged_recipe_input(recipe)
        if merged_in:
            plist["Input"] = dict(merged_in)
    else:
        merged = merged_recipe_input(recipe)
        plist = {
            "Identifier": recipe.identifier,
            "ParentRecipe": recipe.parent_recipe or "",
            "Input": dict(merged) if merged else {},
        }
        if recipe.trust_info:
            plist_trust: dict = {
                "parent_recipes": {},
                "non_core_processors": {},
            }
            for section in ("parent_recipes", "non_core_processors"):
                entries = recipe.trust_info.get(section, {})
                if entries:
                    plist_trust[section] = {
                        k: {
                            "git_hash": "",
                            "sha256_hash": v.get("sha256_hash", ""),
                        }
                        for k, v in entries.items()
                    }
            plist["ParentRecipeTrustInfo"] = plist_trust
    _apply_extract_icon_to_runner_plist(recipe, plist)
    if isinstance(plist.get("Input"), dict):
        plist["Input"] = _coerce_input_scalars_to_str(plist["Input"])
    return plist


def _plist_trust_snippet_from_db_trust(trust_info: dict) -> dict:
    """Build ``ParentRecipeTrustInfo`` plist-shaped dict from canonical DB ``trust_info``."""
    plist_trust: dict = {
        "parent_recipes": {},
        "non_core_processors": {},
    }
    if trust_info.get("parent_recipes"):
        plist_trust["parent_recipes"] = {
            k: {"git_hash": "", "sha256_hash": v.get("sha256_hash", "")}
            for k, v in trust_info["parent_recipes"].items()
        }
    if trust_info.get("non_core_processors"):
        plist_trust["non_core_processors"] = {
            k: {"git_hash": "", "sha256_hash": v.get("sha256_hash", "")}
            for k, v in trust_info["non_core_processors"].items()
        }
    return plist_trust


def _parse_imported_override_content(raw: str) -> dict:
    """
    Parse an override from XML/binary plist, base64 binary plist, JSON object, or YAML.
    """
    s = raw.strip()
    if not s:
        raise HTTPException(status_code=400, detail="Empty content")

    if s.startswith("{"):
        try:
            d = json.loads(s)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e
        if not isinstance(d, dict):
            raise HTTPException(status_code=400, detail="JSON must be an object")
        return d

    try:
        return plistlib.loads(s.encode("utf-8"))
    except Exception:
        pass

    try:
        b = base64.b64decode(s, validate=True)
        return plistlib.loads(b)
    except Exception:
        pass

    try:
        y = yaml.safe_load(s)
    except yaml.YAMLError:
        y = None
    if isinstance(y, dict):
        return y

    raise HTTPException(
        status_code=400,
        detail="Could not parse override (try XML plist, base64 binary plist, JSON object, or YAML)",
    )


router = APIRouter(prefix="/autopkg", tags=["autopkg"])


@router.post("/runs/verify-trust", response_model=VerifyTrustForRunResponse)
async def verify_trust_before_run(
    data: VerifyTrustForRunRequest,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    """
    Re-verify stored trust against GitHub for each recipe that would be included in a run
    (same candidate set as ``GET /autopkg/runs/config``). Updates recipe rows like
    ``POST /autopkg/recipes/{id}/verify-trust``.
    """
    recipes = await list_recipes_for_run(session, data.recipe_names)
    rows, rate_limited = await verify_trust_live_for_recipes(session, recipes)
    await create_audit_entry(
        session,
        action="verify_trust_before_run",
        entity_type="autopkg_run",
        entity_id="batch",
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        after_snapshot={
            "recipe_count": len(rows),
            "rate_limited": rate_limited,
            "names": [r["name"] for r in rows],
        },
    )
    await session.commit()
    return VerifyTrustForRunResponse(
        results=[VerifyTrustForRunRecipeResult(**r) for r in rows],
        rate_limited=rate_limited,
    )


@router.post("/runs", response_model=AutoPkgRunRead)
async def trigger_run(
    data: TriggerRunRequest,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    resolved_runner = normalize_runner_type(data.runner)
    run = await create_and_dispatch_autopkg_run(
        session,
        recipe_names=data.recipe_names,
        runner_type=resolved_runner,
        trigger_type=RunTriggerType.manual_ui,
        triggered_by=user.email if user else "anonymous",
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        audit_action="trigger_run",
    )
    return autopkg_run_to_read(run)


@router.get("/runs", response_model=PaginatedResponse)
async def list_runs(
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: RunStatus | None = Query(None, description="Filter by run status"),
):
    filters = []
    if status is not None:
        filters.append(AutoPkgRun.status == status)

    count_q = select(func.count()).select_from(AutoPkgRun)
    if filters:
        count_q = count_q.where(*filters)
    count = (await session.execute(count_q)).scalar() or 0

    list_q = (
        select(AutoPkgRun)
        .options(selectinload(AutoPkgRun.results), selectinload(AutoPkgRun.schedule))
        .order_by(AutoPkgRun.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if filters:
        list_q = list_q.where(*filters)
    result = await session.execute(list_q)
    runs = result.scalars().unique().all()

    return PaginatedResponse(
        items=[autopkg_run_to_read(r) for r in runs],
        total=count,
        page=page,
        page_size=page_size,
        total_pages=(count + page_size - 1) // page_size,
    )


@router.post("/runs/claim-next-local", response_model=AutoPkgRunRead)
async def claim_next_local_run(session: AsyncSession = Depends(get_session)):
    """Atomically claim the oldest pending **local** run (``FOR UPDATE SKIP LOCKED``).

    Use this from ``poll_local_autopkg.sh`` with ``LOCAL_RUNNER_TOKEN``, or with a normal
    user JWT that has AutoPkg runs write access. Returns **204** when no run is waiting.
    """
    stmt = (
        select(AutoPkgRun)
        .where(AutoPkgRun.runner_type == "local")
        .where(AutoPkgRun.status == RunStatus.pending)
        .order_by(AutoPkgRun.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    async with session.begin():
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()
        if run is None:
            return Response(status_code=204)
        run.status = RunStatus.running
        run.started_at = datetime.now(UTC)
    await session.refresh(run, attribute_names=["schedule"])
    return autopkg_run_to_read(run)


@router.get("/runs/config")
async def get_run_config(
    session: AsyncSession = Depends(get_session),
    recipes: str = Query(None, description="Comma-separated recipe names to include"),
):
    """
    Return the configuration needed by the GitHub Actions runner:
    override plist dicts and the set of repos to autopkg repo-add.

    If `recipes` is provided, only those recipes are included.
    Otherwise all enabled overrides are returned.
    """
    recipe_names: list[str] | None = None
    if recipes:
        recipe_names = [n.strip() for n in recipes.split(",") if n.strip()]
    all_recipes = await list_recipes_for_run(session, recipe_names)

    overrides: list[dict] = []
    repo_urls: set[str] = set()

    for recipe in all_recipes:
        override_entry: dict = {
            "name": recipe.name,
            "identifier": recipe.identifier,
            "plist": _runner_plist_dict_for_recipe(recipe),
        }

        overrides.append(override_entry)

        if recipe.source_repo_full_name:
            repo_urls.add(f"https://github.com/{recipe.source_repo_full_name}.git")
        trust_for_repos = recipe.trust_info
        if not trust_for_repos and recipe.override_data:
            trust_for_repos = recipe.override_data.get("ParentRecipeTrustInfo")
        inferred = infer_repos_from_trust_info(trust_for_repos)
        repo_urls.update(f"https://github.com/{r}.git" for r in inferred)

    return {
        "overrides": overrides,
        "repos": sorted(repo_urls),
        "total_overrides": len(overrides),
        "total_repos": len(repo_urls),
    }


@router.get("/runs/{run_id}", response_model=AutoPkgRunRead)
async def get_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(AutoPkgRun)
        .options(selectinload(AutoPkgRun.results), selectinload(AutoPkgRun.schedule))
        .where(AutoPkgRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return autopkg_run_to_read(run)


@router.post("/runs/{run_id}/github-context", response_model=AutoPkgRunRead)
async def post_github_run_context(
    run_id: uuid.UUID,
    data: GitHubRunContextUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Webhook for the GitHub Actions job to record ``GITHUB_RUN_ID`` and HTML URL."""
    run = await session.get(AutoPkgRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.runner_type != "github":
        raise HTTPException(status_code=400, detail="Run is not a GitHub Actions run")

    rid = str(data.github_run_id).strip()
    url = str(data.github_run_url).strip()
    if not rid or not url:
        raise HTTPException(status_code=400, detail="github_run_id and github_run_url are required")

    run.github_run_id = rid
    run.github_run_url = url
    await session.commit()
    await session.refresh(run, attribute_names=["schedule"])
    return autopkg_run_to_read(run)


@router.get("/schedules", response_model=list[AutoPkgScheduleRead])
async def list_schedules(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(AutoPkgSchedule).order_by(AutoPkgSchedule.name))
    return [AutoPkgScheduleRead.model_validate(x) for x in result.scalars().all()]


@router.post("/schedules", response_model=AutoPkgScheduleRead)
async def create_schedule(
    data: AutoPkgScheduleCreate,
    session: AsyncSession = Depends(get_session),
):
    assert_valid_cron_expression(data.cron_expression)
    assert_valid_timezone(data.timezone)
    if data.recipe_names:
        await ensure_recipe_names_runnable(session, data.recipe_names)
    sch = AutoPkgSchedule(
        name=data.name.strip(),
        cron_expression=data.cron_expression.strip(),
        timezone=data.timezone.strip(),
        recipe_names=data.recipe_names,
        runner_type=data.runner,
        enabled=data.enabled,
    )
    schedule_next_for_row(sch)
    session.add(sch)
    await session.commit()
    await session.refresh(sch)
    return AutoPkgScheduleRead.model_validate(sch)


@router.get("/schedules/{schedule_id}", response_model=AutoPkgScheduleRead)
async def get_schedule(
    schedule_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    sch = await session.get(AutoPkgSchedule, schedule_id)
    if not sch:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return AutoPkgScheduleRead.model_validate(sch)


@router.patch("/schedules/{schedule_id}", response_model=AutoPkgScheduleRead)
async def update_schedule(
    schedule_id: uuid.UUID,
    data: AutoPkgScheduleUpdate,
    session: AsyncSession = Depends(get_session),
):
    sch = await session.get(AutoPkgSchedule, schedule_id)
    if not sch:
        raise HTTPException(status_code=404, detail="Schedule not found")
    was_disabled = not sch.enabled
    patch = data.model_dump(exclude_unset=True)
    if "name" in patch:
        sch.name = patch["name"].strip()
    if "cron_expression" in patch:
        assert_valid_cron_expression(patch["cron_expression"])
        sch.cron_expression = patch["cron_expression"].strip()
    if "timezone" in patch:
        assert_valid_timezone(patch["timezone"])
        sch.timezone = patch["timezone"].strip()
    if "recipe_names" in patch:
        if patch["recipe_names"]:
            await ensure_recipe_names_runnable(session, patch["recipe_names"])
        sch.recipe_names = patch["recipe_names"]
    if "runner" in patch:
        sch.runner_type = patch["runner"]
    if "enabled" in patch:
        sch.enabled = patch["enabled"]
    if sch.enabled:
        if (patch.get("enabled") is True and was_disabled) or "cron_expression" in patch or "timezone" in patch:
            schedule_next_for_row(sch)
    await session.commit()
    await session.refresh(sch)
    return AutoPkgScheduleRead.model_validate(sch)


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    sch = await session.get(AutoPkgSchedule, schedule_id)
    if not sch:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await session.delete(sch)
    await session.commit()
    return Response(status_code=204)


@router.post("/schedules/run-due")
async def run_due_schedules_webhook(
    x_schedule_secret: str | None = Header(None, alias="X-Schedule-Secret"),
):
    if not settings.schedule_webhook_secret:
        raise HTTPException(status_code=503, detail="Schedule webhook secret not configured")
    if not x_schedule_secret or x_schedule_secret != settings.schedule_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid schedule secret")
    await fire_due_schedules()
    async with async_session_factory() as promo_session:
        await run_all_auto_promotions(promo_session)
        await promo_session.commit()
    return {"status": "ok"}


@router.post("/promotions/run-due")
async def run_due_promotions_webhook(
    x_schedule_secret: str | None = Header(None, alias="X-Schedule-Secret"),
):
    """Run legacy auto-time rules + promotion channel tick (same secret as schedules)."""
    if not settings.schedule_webhook_secret:
        raise HTTPException(status_code=503, detail="Schedule webhook secret not configured")
    if not x_schedule_secret or x_schedule_secret != settings.schedule_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid schedule secret")
    async with async_session_factory() as session:
        out = await run_all_auto_promotions(session)
        await session.commit()
    return {"status": "ok", **out}


def _slug_recipe_identifier(identifier: str) -> str:
    """``com.github.autopkg.recipes.Foo`` → ``com.github.autopkg.recipes.Foo`` (safe).

    Anything not in ``[A-Za-z0-9._-]`` collapses to ``_`` so the storage path stays
    a valid blob key on Azure (``//`` and other reserved characters cause 400s).
    """
    s = identifier.strip()
    if not s:
        return "unknown-recipe"
    return re.sub(r"[^\w.\-]+", "_", s, flags=re.UNICODE).strip("._-") or "unknown-recipe"


def _safe_pkg_filename(filename: str | None) -> str:
    """Reject path components and reduce the basename to a safe blob name."""
    if not filename:
        return "upload.pkg"
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = re.sub(r"[^\w.\-]+", "_", base, flags=re.UNICODE).strip("._-")
    return cleaned or "upload.pkg"


@router.post("/runs/{run_id}/pkgs", status_code=201)
async def upload_run_pkg(
    run_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    recipe_identifier: str = Form(...),
    relative_path: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    """Stream a runner-produced pkg/dmg into the configured storage backend.

    Called by ``AutoPkg/scripts/report_results.py`` (cloud + local runners) right
    before ``POST /runs/{id}/results``. When ``STORAGE_BACKEND=none`` the
    response is ``503`` so the runner can fall back to path-only reporting and
    keep existing manual-sync workflows intact.

    Auth: ``Authorization: Bearer <LOCAL_RUNNER_TOKEN>`` (see
    ``rbac_middleware._local_runner_authenticated_path``).
    """
    run = await session.get(AutoPkgRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status not in (RunStatus.running, RunStatus.pending):
        raise HTTPException(
            status_code=409,
            detail=f"Run is {run.status}; pkg uploads are only accepted while running",
        )

    if relative_path.strip():
        try:
            rel = sanitize_relative_path(relative_path)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
    else:
        slug = _slug_recipe_identifier(recipe_identifier)
        fname = _safe_pkg_filename(file.filename)
        rel = f"pkgs/{slug}/{fname}"

    backend = get_storage_backend()

    async def _stream() -> AsyncIterator[bytes]:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            yield chunk

    try:
        url = await backend.upload(
            relative_path=rel,
            body=_stream(),
            content_length=None,
            content_type=file.content_type or "application/octet-stream",
        )
    except StorageNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        # Without this, an exception from inside the SDK (network, auth,
        # mis-configured kwarg, etc.) bubbles to uvicorn's default handler,
        # which produces a plain-text "Internal Server Error" 500 with no
        # body — the runner then prints the useless "HTTP 500: Internal
        # Server Error" we used to see for the broken ``max_single_put_size``
        # kwarg. Wrap it in a JSON HTTPException so the runner / UI gets
        # actionable detail, and log the full traceback for the backend
        # logs.
        logger.exception(
            "pkg_upload_failed",
            relative_path=rel,
            recipe_identifier=recipe_identifier,
            backend=type(backend).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Storage backend upload failed: {type(e).__name__}: {e}",
        ) from e

    background_tasks.add_task(backend.invalidate_cdn, [rel])
    return {"imported_pkg_url": url, "relative_path": rel}


@router.post("/runs/{run_id}/results", response_model=RunResultRead)
async def post_run_result(
    run_id: uuid.UUID,
    data: RunResultCreate,
    session: AsyncSession = Depends(get_session),
):
    """Webhook endpoint for the AutoPkg runner to POST per-recipe results."""
    run = await session.get(AutoPkgRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    recipe_result = AutoPkgRunResult(
        run_id=run_id,
        recipe_identifier=data.recipe_identifier,
        recipe_name=data.recipe_name,
        status=RecipeResultStatus(data.status),
        imported_version=data.imported_version,
        imported_display_name=data.imported_display_name,
        imported_pkg_path=data.imported_pkg_path,
        imported_pkg_url=data.imported_pkg_url,
        imported_pkginfo_path=data.imported_pkginfo_path,
        imported_catalogs=data.imported_catalogs,
        virustotal_results=data.virustotal_results,
        trust_info_diff=data.trust_info_diff,
        log_output=data.log_output,
        error_message=data.error_message,
        duration_seconds=data.duration_seconds,
    )

    recipe_obj = (
        await session.execute(select(AutoPkgRecipe).where(AutoPkgRecipe.identifier == data.recipe_identifier))
    ).scalar_one_or_none()

    # Match DB row when report script sent a mismatched identifier (e.g. filename heuristics).
    if recipe_obj is None and data.recipe_name:
        name_key = data.recipe_name.strip().lower()
        alt = (
            (await session.execute(select(AutoPkgRecipe).where(func.lower(AutoPkgRecipe.name) == name_key)))
            .scalars()
            .all()
        )
        if len(alt) == 1:
            recipe_obj = alt[0]

    if recipe_obj:
        recipe_obj.last_run_at = datetime.now(UTC)
        recipe_obj.last_run_status = data.status

    if data.status == "trust_failed":
        recipe_result.approval_status = ApprovalStatus.pending
    elif recipe_obj and recipe_obj.auto_promote:
        recipe_result.approval_status = ApprovalStatus.auto_approved
    elif data.status == "imported":
        # Must match ``ingest_pkginfo`` / ``_get_quarantine_catalog`` gating: managed
        # recipes with auto-promote off are staged in quarantine with
        # ``pending_catalog_names`` and need a human "import" approval. Imports
        # without a matching DB row publish pkginfo to plist catalogs directly.
        use_quarantine = bool(recipe_obj is not None and not recipe_obj.auto_promote)
        recipe_result.approval_status = ApprovalStatus.pending if use_quarantine else ApprovalStatus.auto_approved
    else:
        recipe_result.approval_status = ApprovalStatus.auto_approved

    session.add(recipe_result)
    await session.commit()
    await session.refresh(recipe_result)
    return RunResultRead.model_validate(recipe_result)


@router.post("/runs/{run_id}/complete")
async def complete_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Called by the runner when the entire run is complete."""
    result = await session.execute(
        select(AutoPkgRun).options(selectinload(AutoPkgRun.results)).where(AutoPkgRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    run.status = RunStatus.completed
    run.completed_at = datetime.now(UTC)
    run.total_recipes = len(run.results)
    run.recipes_succeeded = sum(
        1 for r in run.results if r.status in (RecipeResultStatus.success, RecipeResultStatus.no_change)
    )
    run.recipes_failed = sum(
        1 for r in run.results if r.status in (RecipeResultStatus.failed, RecipeResultStatus.trust_failed)
    )
    run.recipes_imported = sum(1 for r in run.results if r.status == RecipeResultStatus.imported)

    await session.commit()
    return {"message": "Run completed", "run_id": str(run_id)}


def _recipe_input_dict(recipe: AutoPkgRecipe) -> dict | None:
    """Effective ``Input`` from ``input_variables`` merged with ``override_data.Input`` (override wins)."""
    m = merged_recipe_input(recipe)
    return m if m else None


def _recipe_audit_snapshot(recipe: AutoPkgRecipe) -> dict:
    """Stable recipe state for audit before/after snapshots (editable DB fields only)."""
    return {
        "identifier": recipe.identifier,
        "name": recipe.name,
        "parent_recipe": recipe.parent_recipe,
        "source_repo_full_name": recipe.source_repo_full_name,
        "is_enabled": recipe.is_enabled,
        "extract_icon_enabled": recipe.extract_icon_enabled,
        "auto_promote": recipe.auto_promote,
        "promotion_channel_id": str(recipe.promotion_channel_id) if recipe.promotion_channel_id else None,
        "override_data": recipe.override_data,
        "trust_info": recipe.trust_info,
        "input_variables": recipe.input_variables,
        "trust_status": recipe.trust_status,
    }


def _recipe_pkginfo_key(recipe: AutoPkgRecipe) -> str:
    inp = _recipe_input_dict(recipe)
    if isinstance(inp, dict):
        n = inp.get("NAME")
        if isinstance(n, str) and n.strip():
            return n.strip()
    return recipe.name


def _get_override_pkginfo_dict(recipe: AutoPkgRecipe) -> dict | None:
    """``Input.pkginfo`` from merged DB Input (override plist + any ``input_variables``), if present.

    ``%VAR%`` references inside the override's pkginfo (e.g. ``category =
    "%MUNKI_CATEGORY%"`` in the Blender recipe) are substituted using the
    rest of the merged Input as the lookup table, mirroring what AutoPkg
    does on disk via ``process_cli_overrides``. Without this, the literal
    ``%MUNKI_CATEGORY%`` string would clobber AutoPkg's correctly-substituted
    value when ``_merge_plist_with_override_pkginfo`` merges the override
    on top of the ingested plist.
    """
    inp = merged_recipe_input(recipe)
    if "pkginfo" not in inp:
        return None
    pkginfo = inp.get("pkginfo")
    if not isinstance(pkginfo, dict):
        return None
    return substitute_input_vars(pkginfo, inp)


def _merge_plist_with_override_pkginfo(plist: dict, override_pkginfo: dict) -> dict:
    """Apply ``Input.pkginfo`` from the DB override on top of the plist AutoPkg wrote.

    ``name`` and ``version`` always come from the ingested plist (resolved on disk);
    everything else in the override wins when present.
    """
    merged = dict(plist)
    name, version = merged.get("name"), merged.get("version")
    merged.update(override_pkginfo)
    if name is not None:
        merged["name"] = name
    if version is not None:
        merged["version"] = version
    return merged


def _pkginfo_kwargs_from_plist(plist: dict) -> dict:
    """Map a pkginfo plist dict to :class:`PkgInfo` constructor / column kwargs."""
    return {
        "name": plist["name"],
        "version": plist["version"],
        "display_name": plist.get("display_name"),
        "description": plist.get("description"),
        "category": plist.get("category"),
        "developer": plist.get("developer"),
        "icon_name": plist.get("icon_name"),
        "installer_item_location": plist.get("installer_item_location"),
        "installer_item_hash": plist.get("installer_item_hash"),
        "installer_item_size": plist.get("installer_item_size"),
        "installed_size": plist.get("installed_size"),
        "installer_type": plist.get("installer_type"),
        "minimum_os_version": plist.get("minimum_os_version"),
        "maximum_os_version": plist.get("maximum_os_version"),
        "uninstall_method": plist.get("uninstall_method"),
        "unattended_install": plist.get("unattended_install", False),
        "unattended_uninstall": plist.get("unattended_uninstall", False),
        "autoremove": plist.get("autoremove", False),
        "uninstallable": plist.get("uninstallable", True),
        "installs": plist.get("installs"),
        "receipts": plist.get("receipts"),
        "blocking_applications": plist.get("blocking_applications"),
        "items_to_copy": plist.get("items_to_copy"),
        "supported_architectures": plist.get("supported_architectures"),
        "requires": plist.get("requires"),
        "update_for": plist.get("update_for"),
        "preinstall_script": plist.get("preinstall_script"),
        "postinstall_script": plist.get("postinstall_script"),
        "preuninstall_script": plist.get("preuninstall_script"),
        "postuninstall_script": plist.get("postuninstall_script"),
        "installcheck_script": plist.get("installcheck_script"),
        "uninstallcheck_script": plist.get("uninstallcheck_script"),
        "metadata_": plist.get("_metadata"),
    }


def _apply_pkginfo_kwargs_to_row(pkg: PkgInfo, kwargs: dict) -> None:
    """Set pkginfo columns from kwargs."""
    for key, val in kwargs.items():
        setattr(pkg, key, val)


def _apply_recipe_identifier_to_pkginfo_metadata(kwargs: dict, recipe_identifier: str | None) -> None:
    if not recipe_identifier:
        return
    base = kwargs.get("metadata_")
    md: dict
    if isinstance(base, dict):
        md = dict(base)
    elif base is None:
        md = {}
    else:
        md = {}
    md[PKGINFO_METADATA_RECIPE_IDENTIFIER_KEY] = recipe_identifier
    kwargs["metadata_"] = md


async def _batch_pkginfo_labels(session: AsyncSession, names: list[str]) -> dict[str, tuple[str | None, str | None]]:
    """Latest ``PkgInfo`` row per ``name`` (by ``updated_at``) for display/icon labels."""
    if not names:
        return {}
    result = await session.execute(
        select(PkgInfo).where(
            PkgInfo.is_deleted.is_(False),
            PkgInfo.name.in_(names),
        )
    )
    rows = result.scalars().all()
    best: dict[str, PkgInfo] = {}
    for p in rows:
        cur = best.get(p.name)
        if cur is None:
            best[p.name] = p
            continue
        if p.updated_at is None:
            continue
        if cur.updated_at is None or p.updated_at > cur.updated_at:
            best[p.name] = p
    out: dict[str, tuple[str | None, str | None]] = {}
    for name, pkg in best.items():
        dn = pkg.display_name.strip() if pkg.display_name and pkg.display_name.strip() else None
        ic = pkg.icon_name.strip() if pkg.icon_name and pkg.icon_name.strip() else None
        out[name] = (dn, ic)
    return out


def _enrich_recipe_read(
    recipe: AutoPkgRecipe,
    labels: dict[str, tuple[str | None, str | None]],
) -> AutoPkgRecipeRead:
    key = _recipe_pkginfo_key(recipe)
    pair = labels.get(key)
    base = AutoPkgRecipeRead.model_validate(recipe)
    if pair is None:
        return base.model_copy(update={"pkginfo_display_name": None, "pkginfo_icon_name": None})
    return base.model_copy(
        update={
            "pkginfo_display_name": pair[0],
            "pkginfo_icon_name": pair[1],
        }
    )


def _recipe_list_filter_clauses(
    *,
    enabled_only: bool,
    enabled: str | None,
    search: str | None,
    trust_status: TrustStatus | None = None,
) -> list:
    clauses: list = []
    if enabled_only:
        clauses.append(AutoPkgRecipe.is_enabled.is_(True))
    elif enabled == "true":
        clauses.append(AutoPkgRecipe.is_enabled.is_(True))
    elif enabled == "false":
        clauses.append(AutoPkgRecipe.is_enabled.is_(False))
    if trust_status is not None:
        clauses.append(AutoPkgRecipe.trust_status == trust_status.value)
    if search and search.strip():
        term = f"%{search.strip()}%"
        clauses.append(
            or_(
                AutoPkgRecipe.name.ilike(term),
                AutoPkgRecipe.identifier.ilike(term),
                AutoPkgRecipe.parent_recipe.ilike(term),
                AutoPkgRecipe.source_repo_full_name.ilike(term),
            )
        )
    return clauses


@router.get("/recipes", response_model=PaginatedResponse)
async def list_recipes(
    session: AsyncSession = Depends(get_session),
    enabled_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=1000),
    search: str | None = Query(None),
    enabled: str | None = Query(None, description="Filter: 'true', 'false', or omit for all"),
    trust_status: TrustStatus | None = Query(
        None,
        description="Filter by trust status (verified, failed, pending_approval, unknown)",
    ),
):
    clauses = _recipe_list_filter_clauses(
        enabled_only=enabled_only,
        enabled=enabled,
        search=search,
        trust_status=trust_status,
    )
    count_stmt = select(func.count()).select_from(AutoPkgRecipe)
    if clauses:
        count_stmt = count_stmt.where(and_(*clauses))
    count = (await session.execute(count_stmt)).scalar() or 0

    query = select(AutoPkgRecipe).order_by(AutoPkgRecipe.name)
    if clauses:
        query = query.where(and_(*clauses))
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    recipes = result.scalars().all()
    keys = list({_recipe_pkginfo_key(r) for r in recipes})
    labels = await _batch_pkginfo_labels(session, keys)
    items = [_enrich_recipe_read(r, labels) for r in recipes]
    total_pages = (count + page_size - 1) // page_size if count else 0
    return PaginatedResponse(
        items=items,
        total=count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# Static /recipes/* paths must be registered before /recipes/{recipe_id} so segments
# like "discover", "search", and "trust-status" are not parsed as UUIDs (422).


@router.get("/recipes/discover", response_model=list[GitHubRecipeRepoRead])
async def discover_recipes(session: AsyncSession = Depends(get_session)):
    """List all cached GitHub recipe repos from the local DB."""
    result = await session.execute(
        select(GitHubRecipeRepo)
        .options(selectinload(GitHubRecipeRepo.cached_recipes))
        .order_by(GitHubRecipeRepo.stars.desc(), GitHubRecipeRepo.name)
    )
    repos = result.scalars().unique().all()
    return [GitHubRecipeRepoRead.model_validate(r) for r in repos]


@router.get("/recipes/discover/{repo_owner}/{repo_name}")
async def discover_repo_recipes(
    repo_owner: str,
    repo_name: str,
    session: AsyncSession = Depends(get_session),
):
    """List cached recipes for a specific repo. If none cached, fetch live."""
    full_name = f"{repo_owner}/{repo_name}"
    repo = (
        await session.execute(
            select(GitHubRecipeRepo)
            .options(selectinload(GitHubRecipeRepo.cached_recipes))
            .where(GitHubRecipeRepo.full_name == full_name)
        )
    ).scalar_one_or_none()

    if repo and repo.cached_recipes:
        recipes = [
            {
                "name": r.name,
                "filename": r.filename,
                "path": r.path,
                "identifier_guess": r.identifier_guess,
                "repo_full_name": full_name,
                "url": r.url,
            }
            for r in repo.cached_recipes
        ]
        return {
            "recipes": recipes,
            "total": len(recipes),
            "repo": full_name,
            "cached": True,
        }

    recipes = await discover_recipes_in_repo(full_name)
    if repo and recipes:
        await sync_repo_recipes_to_cache(session, repo)
    return {
        "recipes": recipes,
        "total": len(recipes),
        "repo": full_name,
        "cached": False,
    }


@router.get("/recipes/search")
async def search_recipes(
    q: str = Query(..., min_length=2),
    session: AsyncSession = Depends(get_session),
):
    """Search locally cached recipes by name, path, or identifier."""
    pattern = f"%{q}%"
    result = await session.execute(
        select(GitHubRecipe)
        .where(
            or_(
                GitHubRecipe.name.ilike(pattern),
                GitHubRecipe.path.ilike(pattern),
                GitHubRecipe.identifier_guess.ilike(pattern),
            )
        )
        .options(selectinload(GitHubRecipe.repo))
        .limit(200)
    )
    recipes = result.scalars().all()
    results = [
        {
            "name": r.name,
            "filename": r.filename,
            "path": r.path,
            "identifier_guess": r.identifier_guess,
            "repo_full_name": r.repo.full_name if r.repo else "",
            "repo_name": r.repo.name if r.repo else "",
            "repo_url": r.repo.html_url if r.repo else "",
            "url": r.url,
        }
        for r in recipes
    ]
    return {"results": results, "total": len(results)}


@router.get("/recipes/trust-status", response_model=list[AutoPkgRecipeRead])
async def list_trust_status(
    session: AsyncSession = Depends(get_session),
    status: str | None = Query(None),
):
    """List all recipes with their trust status. Optionally filter by status."""
    query = select(AutoPkgRecipe).order_by(AutoPkgRecipe.name)
    if status:
        query = query.where(AutoPkgRecipe.trust_status == status)
    result = await session.execute(query)
    recipes = result.scalars().all()
    keys = list({_recipe_pkginfo_key(r) for r in recipes})
    labels = await _batch_pkginfo_labels(session, keys)
    return [_enrich_recipe_read(r, labels) for r in recipes]


@router.get("/recipes/trust-summary", response_model=RecipeTrustSummaryResponse)
async def recipe_trust_summary(session: AsyncSession = Depends(get_session)):
    """Count overrides grouped by stored trust status (for dashboard widgets)."""
    result = await session.execute(
        select(AutoPkgRecipe.trust_status, func.count()).group_by(AutoPkgRecipe.trust_status)
    )
    counts = {
        TrustStatus.verified.value: 0,
        TrustStatus.failed.value: 0,
        TrustStatus.pending_approval.value: 0,
        TrustStatus.unknown.value: 0,
    }
    for row in result.all():
        status, n = row[0], int(row[1])
        if status in counts:
            counts[status] = n
    return RecipeTrustSummaryResponse(
        verified=counts[TrustStatus.verified.value],
        failed=counts[TrustStatus.failed.value],
        pending_approval=counts[TrustStatus.pending_approval.value],
        unknown=counts[TrustStatus.unknown.value],
    )


@router.get("/recipes/{recipe_id}", response_model=AutoPkgRecipeRead)
async def get_recipe(
    recipe_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    recipe = await session.get(AutoPkgRecipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    key = _recipe_pkginfo_key(recipe)
    labels = await _batch_pkginfo_labels(session, [key])
    return _enrich_recipe_read(recipe, labels)


@router.get("/recipes/{recipe_id}/runner-override.plist")
async def download_runner_override_plist(
    recipe_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """
    XML plist of the override in the same form as ``overrides[].plist`` in
    ``GET /autopkg/runs/config`` (including merged DB trust for runners).
    """
    recipe = await session.get(AutoPkgRecipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    plist_dict = _runner_plist_dict_for_recipe(recipe)
    body = plistlib.dumps(plist_dict, fmt=plistlib.FMT_XML)
    safe_name = re.sub(r"[^\w.\-]+", "_", recipe.name).strip("._") or "override"
    filename = f"{safe_name}.recipe.plist"
    return Response(
        content=body,
        media_type="application/x-plist",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/recipes", response_model=AutoPkgRecipeRead)
async def create_recipe(
    data: AutoPkgRecipeCreate,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    existing = await session.execute(select(AutoPkgRecipe).where(AutoPkgRecipe.identifier == data.identifier))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Recipe already exists")

    recipe = AutoPkgRecipe(**data.model_dump(exclude={"github_repo", "recipe_path"}))
    _normalize_pkginfo_into_override_only(recipe)
    session.add(recipe)

    await create_audit_entry(
        session,
        action="create",
        entity_type="autopkg_recipe",
        entity_id=str(recipe.id),
        entity_name=recipe.name,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
    )

    await session.commit()
    await session.refresh(recipe)
    return AutoPkgRecipeRead.model_validate(recipe)


@router.post("/recipes/import-override", response_model=AutoPkgRecipeRead)
async def import_recipe_override(
    data: AutoPkgRecipeImportOverrideRequest,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    """
    Import an existing AutoPkg override plist (from ``RecipeOverrides`` or a repo)
    into ``autopkg_recipe``. Optionally re-resolve trust from GitHub.
    """
    parsed = _parse_imported_override_content(data.content)
    identifier = parsed.get("Identifier")
    parent_recipe = parsed.get("ParentRecipe")
    if not identifier or not isinstance(identifier, str):
        raise HTTPException(status_code=400, detail="Override must include a string Identifier")
    if not parent_recipe or not isinstance(parent_recipe, str):
        raise HTTPException(
            status_code=400,
            detail="Override must include a string ParentRecipe (this must be an override, not a full recipe)",
        )

    existing = await session.execute(select(AutoPkgRecipe).where(AutoPkgRecipe.identifier == identifier))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A recipe with this identifier already exists")

    input_dict = dict(parsed.get("Input") or {})
    input_variables_for_db = _strip_pkginfo_from_input(input_dict if input_dict else None)

    name = (data.name or "").strip() or identifier.rsplit(".", 1)[-1]

    source_repo: str | None = None
    if data.source_repo_full_name and str(data.source_repo_full_name).strip():
        try:
            source_repo = normalize_github_full_name(str(data.source_repo_full_name))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    override_plist: dict = {
        "Identifier": identifier,
        "ParentRecipe": parent_recipe,
        "Input": input_dict,
    }
    for key in ("MinimumVersion", "Process"):
        if key in parsed:
            override_plist[key] = parsed[key]
    if isinstance(parsed.get("ParentRecipeTrustInfo"), dict):
        override_plist["ParentRecipeTrustInfo"] = parsed["ParentRecipeTrustInfo"]

    plist_trust_raw = parsed.get("ParentRecipeTrustInfo")
    trust_from_plist = (
        trust_info_from_plist_parent_recipe_trust(plist_trust_raw) if isinstance(plist_trust_raw, dict) else None
    )

    trust_info: dict | None = None
    trust_status = TrustStatus.unknown.value
    trust_verified_at = None

    if data.refresh_trust:
        location_cache = await build_location_cache(session)
        try:
            new_trust = await compute_trust_info(
                parent_recipe,
                existing_trust_info=trust_from_plist,
                location_cache=location_cache,
            )
        except GitHubRateLimitError:
            raise HTTPException(
                status_code=503,
                detail="GitHub API rate limit exceeded. Try again later or import with refresh_trust=false.",
            ) from None
        except GitHubForbiddenError as exc:
            msg = exc.github_message or "forbidden"
            raise HTTPException(
                status_code=502,
                detail=(
                    f"GitHub denied access: {msg}. Check that the configured "
                    "GITHUB_TOKEN has read access to the recipe repos."
                ),
            ) from None
        if new_trust.get("parent_recipes"):
            trust_info = new_trust
            trust_status = TrustStatus.verified.value
            trust_verified_at = datetime.now(UTC)
            override_plist["ParentRecipeTrustInfo"] = _plist_trust_snippet_from_db_trust(new_trust)
        elif trust_from_plist and (
            trust_from_plist.get("parent_recipes") or trust_from_plist.get("non_core_processors")
        ):
            trust_info = trust_from_plist
    elif trust_from_plist and (trust_from_plist.get("parent_recipes") or trust_from_plist.get("non_core_processors")):
        trust_info = trust_from_plist

    recipe = AutoPkgRecipe(
        identifier=identifier,
        name=name,
        parent_recipe=parent_recipe,
        source_repo_full_name=source_repo,
        override_data=override_plist,
        trust_info=trust_info,
        input_variables=input_variables_for_db,
        is_enabled=data.is_enabled,
        auto_promote=data.auto_promote,
        trust_status=trust_status,
        trust_verified_at=trust_verified_at,
    )
    _normalize_pkginfo_into_override_only(recipe)
    session.add(recipe)

    await create_audit_entry(
        session,
        action="import_override",
        entity_type="autopkg_recipe",
        entity_id=str(recipe.id),
        entity_name=recipe.name,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        after_snapshot={"identifier": identifier, "refresh_trust": data.refresh_trust},
    )

    await session.commit()
    await session.refresh(recipe)
    return AutoPkgRecipeRead.model_validate(recipe)


@router.put("/recipes/{recipe_id}", response_model=AutoPkgRecipeRead)
async def update_recipe(
    recipe_id: uuid.UUID,
    data: AutoPkgRecipeUpdate,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    recipe = await session.get(AutoPkgRecipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    before = _recipe_audit_snapshot(recipe)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(recipe, field, value)

    _normalize_pkginfo_into_override_only(recipe)
    after = _recipe_audit_snapshot(recipe)

    await create_audit_entry(
        session,
        action="update",
        entity_type="autopkg_recipe",
        entity_id=str(recipe_id),
        entity_name=recipe.name,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        before_snapshot=before,
        after_snapshot=after,
        changes=update_data,
    )

    await session.commit()
    await session.refresh(recipe)
    return AutoPkgRecipeRead.model_validate(recipe)


@router.delete("/recipes/{recipe_id}")
async def delete_recipe(
    recipe_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    recipe = await session.get(AutoPkgRecipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    before = _recipe_audit_snapshot(recipe)

    await create_audit_entry(
        session,
        action="delete",
        entity_type="autopkg_recipe",
        entity_id=str(recipe_id),
        entity_name=recipe.name,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        before_snapshot=before,
    )

    await session.delete(recipe)
    await session.commit()
    return {"message": f"Recipe {recipe.name} deleted"}


# ── Trust verification ────────────────────────────────────────────────────


@router.post("/recipes/{recipe_id}/verify-trust")
async def verify_recipe_trust(
    recipe_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    """
    Verify trust for a single recipe by comparing stored trust_info
    against freshly computed hashes from GitHub.
    """
    recipe = await session.get(AutoPkgRecipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    location_cache = await build_location_cache(session)
    result = await verify_trust(
        stored_trust_info=recipe.trust_info,
        parent_recipe_identifier=recipe.parent_recipe,
        location_cache=location_cache,
    )

    await persist_verify_trust_result(session, recipe, result, location_cache)

    await create_audit_entry(
        session,
        action="verify_trust",
        entity_type="autopkg_recipe",
        entity_id=str(recipe_id),
        entity_name=recipe.name,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        notes=f"Trust status: {result.status}" + (f" - {result.error}" if result.error else ""),
    )

    await session.commit()
    await session.refresh(recipe)
    return {
        "recipe_id": str(recipe_id),
        "name": recipe.name,
        "trust_status": recipe.trust_status,
        "diff": result.diff if result.diff else None,
        "error": result.error,
    }


@router.post("/recipes/{recipe_id}/update-trust")
async def update_recipe_trust(
    recipe_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    """
    Update trust info for a recipe with freshly computed values.
    Re-resolves all parent recipes and stores github_repo/github_path
    for fast future verification. Should only be called after approval.
    """
    recipe = await session.get(AutoPkgRecipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    location_cache = await build_location_cache(session)

    try:
        new_trust = await compute_trust_info(
            recipe.parent_recipe,
            existing_trust_info=recipe.trust_info,
            location_cache=location_cache,
        )
    except GitHubRateLimitError:
        raise HTTPException(
            status_code=503,
            detail="GitHub API rate limit exceeded. Please try again later.",
        )
    except GitHubForbiddenError as exc:
        msg = exc.github_message or "forbidden"
        raise HTTPException(
            status_code=502,
            detail=(
                f"GitHub denied access while refreshing trust: {msg}. Check "
                "that the configured GITHUB_TOKEN has read access to the recipe repos."
            ),
        ) from None

    if not new_trust.get("parent_recipes"):
        raise HTTPException(
            status_code=502,
            detail="Could not resolve parent recipes from GitHub. Check that the parent recipe identifier is correct.",
        )

    old_trust = recipe.trust_info
    recipe.trust_info = new_trust
    recipe.trust_status = "verified"
    recipe.trust_verified_at = datetime.now(UTC)
    recipe.trust_approved_by = user.email if user else "system"
    recipe.trust_approved_at = datetime.now(UTC)

    plist_trust = _plist_trust_snippet_from_db_trust(new_trust)
    if recipe.override_data is not None:
        od = dict(recipe.override_data)
        od["ParentRecipeTrustInfo"] = plist_trust
        recipe.override_data = od

    await create_audit_entry(
        session,
        action="update_trust",
        entity_type="autopkg_recipe",
        entity_id=str(recipe_id),
        entity_name=recipe.name,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        before_snapshot={"trust_info": old_trust},
        after_snapshot={"trust_info": new_trust},
    )

    await session.commit()
    return {
        "recipe_id": str(recipe_id),
        "name": recipe.name,
        "trust_status": "verified",
    }


@router.post("/recipes/{recipe_id}/approve-trust")
async def approve_recipe_trust(
    recipe_id: uuid.UUID,
    data: TrustApprovalRequest,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    """
    Approve or reject a pending trust change. If approved, updates the
    stored trust_info with the new computed values.
    """
    recipe = await session.get(AutoPkgRecipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    pending_requests = await session.execute(
        select(TrustChangeRequest)
        .where(TrustChangeRequest.recipe_id == recipe_id)
        .where(TrustChangeRequest.status == "pending")
        .order_by(TrustChangeRequest.requested_at.desc())
    )
    change_request = pending_requests.scalars().first()
    if not change_request:
        raise HTTPException(status_code=400, detail="No pending trust change request")

    reviewer = user.email if user else "anonymous"
    now = datetime.now(UTC)

    if data.approved:
        change_request.status = "approved"
        change_request.reviewed_by = reviewer
        change_request.reviewed_at = now
        change_request.comment = data.comment

        new_trust = change_request.new_trust_info
        recipe.trust_info = new_trust
        recipe.trust_status = "verified"
        recipe.trust_approved_by = reviewer
        recipe.trust_approved_at = now
        plist_trust = _plist_trust_snippet_from_db_trust(new_trust)
        if recipe.override_data is not None:
            od = dict(recipe.override_data)
            od["ParentRecipeTrustInfo"] = plist_trust
            recipe.override_data = od
    else:
        change_request.status = "rejected"
        change_request.reviewed_by = reviewer
        change_request.reviewed_at = now
        change_request.comment = data.comment

        recipe.trust_status = "failed"

    await create_audit_entry(
        session,
        action="approve_trust" if data.approved else "reject_trust",
        entity_type="autopkg_recipe",
        entity_id=str(recipe_id),
        entity_name=recipe.name,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        notes=data.comment,
    )

    await session.commit()
    return {
        "recipe_id": str(recipe_id),
        "name": recipe.name,
        "trust_status": recipe.trust_status,
        "approved": data.approved,
    }


@router.get(
    "/trust-changes/pending-count",
    response_model=TrustPendingCountResponse,
)
async def pending_trust_changes_count(session: AsyncSession = Depends(get_session)):
    """Return how many trust change requests are waiting for approval (sidebar badge)."""
    n = await session.scalar(
        select(func.count()).select_from(TrustChangeRequest).where(TrustChangeRequest.status == "pending")
    )
    return TrustPendingCountResponse(count=int(n or 0))


@router.get(
    "/trust-changes",
    response_model=list[TrustChangeRequestRead],
)
async def list_trust_changes(
    session: AsyncSession = Depends(get_session),
    status: str | None = Query(None),
):
    """List trust change requests, optionally filtered by status."""
    query = select(TrustChangeRequest).order_by(TrustChangeRequest.requested_at.desc())
    if status:
        query = query.where(TrustChangeRequest.status == status)
    result = await session.execute(query)
    return [TrustChangeRequestRead.model_validate(r) for r in result.scalars().all()]


@router.post(
    "/trust/resolve-commit",
    response_model=TrustCommitResolveResponse,
)
async def resolve_trust_commit(
    data: TrustCommitResolveRequest,
    user: User | None = Depends(current_optional_user),
):
    """
    Map a trust hash diff to a GitHub commit URL by walking recent history
    for the file and matching SHA-256 content hashes (not git blob SHAs).
    """
    _ = user  # auth required via dependency
    repo = data.github_repo.strip().removesuffix("/")
    if repo.count("/") != 1 or ".." in repo or repo.startswith("/"):
        raise HTTPException(status_code=400, detail="github_repo must be owner/repo")
    path = data.github_path.strip().lstrip("/")
    if not path or any(p in ("", ".", "..") for p in path.split("/")):
        raise HTTPException(status_code=400, detail="Invalid github_path")

    new_h = data.new_sha256.strip().lower()
    old_h = data.old_sha256.strip().lower() if data.old_sha256 else None
    if not new_h:
        raise HTTPException(status_code=400, detail="new_sha256 is required")

    try:
        sha = await resolve_introducing_commit(repo, path, new_h, old_h)
    except GitHubRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail="GitHub API rate limit exceeded. Try again later.",
        ) from exc
    except GitHubForbiddenError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub denied access: {exc.github_message or 'forbidden'}.",
        ) from exc

    if not sha:
        return TrustCommitResolveResponse(commit_sha=None, commit_url=None)
    return TrustCommitResolveResponse(
        commit_sha=sha,
        commit_url=f"https://github.com/{repo}/commit/{sha}",
    )


@router.post("/repos/update")
async def update_repos_and_verify_trust(
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    """
    Trigger a 'repo update': re-fetch recipe file hashes from GitHub
    for all enabled overrides, then run trust verification on each.
    Returns a summary of results.
    """
    result = await session.execute(
        select(AutoPkgRecipe).where(
            AutoPkgRecipe.is_enabled.is_(True),
            AutoPkgRecipe.trust_info.isnot(None),
        )
    )
    recipes = result.scalars().all()

    summary = {"total": len(recipes), "verified": 0, "failed": 0, "errors": 0}

    location_cache = await build_location_cache(session)

    rate_limited = False
    for recipe in recipes:
        if rate_limited:
            summary["errors"] += 1
            continue
        try:
            verification = await verify_trust(
                stored_trust_info=recipe.trust_info,
                parent_recipe_identifier=recipe.parent_recipe,
                location_cache=location_cache,
            )
            recipe.trust_verified_at = datetime.now(UTC)

            if verification.status == "verified":
                recipe.trust_status = "verified"
                summary["verified"] += 1
            elif verification.status == "failed":
                recipe.trust_status = "pending_approval"

                new_trust = await compute_trust_info(
                    recipe.parent_recipe,
                    existing_trust_info=recipe.trust_info,
                    location_cache=location_cache,
                )
                change_request = TrustChangeRequest(
                    recipe_id=recipe.id,
                    old_trust_info=recipe.trust_info,
                    new_trust_info=new_trust,
                    diff=verification.diff,
                    status="pending",
                )
                session.add(change_request)
                summary["failed"] += 1
            elif verification.error and "rate limit" in verification.error.lower():
                rate_limited = True
                summary["errors"] += 1
            else:
                summary["errors"] += 1
        except GitHubRateLimitError:
            rate_limited = True
            summary["errors"] += 1
        except Exception:
            summary["errors"] += 1

    if rate_limited:
        summary["rate_limited"] = True

    await create_audit_entry(
        session,
        action="repo_update",
        entity_type="autopkg_system",
        entity_id="trust_verification",
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        after_snapshot=summary,
    )

    await session.commit()
    return summary


# ── GitHub cache sync ────────────────────────────────────────────────────


@router.post("/cache/sync-repos")
async def sync_repos(session: AsyncSession = Depends(get_session)):
    """Sync the list of autopkg recipe repos from GitHub into the local cache."""
    result = await sync_repos_to_cache(session)
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])
    return result


@router.post("/cache/sync-recipes")
async def sync_recipes(session: AsyncSession = Depends(get_session)):
    """Sync all recipes for all cached repos. This can take a while."""
    return await sync_all_recipes_to_cache(session)


@router.post("/cache/sync-repo/{repo_owner}/{repo_name}")
async def sync_single_repo(
    repo_owner: str,
    repo_name: str,
    session: AsyncSession = Depends(get_session),
):
    """Sync recipes for a single cached repo."""
    full_name = f"{repo_owner}/{repo_name}"
    repo = (
        await session.execute(select(GitHubRecipeRepo).where(GitHubRecipeRepo.full_name == full_name))
    ).scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not in cache. Sync repos first.")
    count = await sync_repo_recipes_to_cache(session, repo)
    return {"repo": full_name, "recipes_synced": count}


@router.post("/cache/repos", response_model=GitHubRecipeRepoRead)
async def add_manual_github_repo(
    data: GitHubCustomRepoAdd,
    session: AsyncSession = Depends(get_session),
):
    """Add any public GitHub repo to the discover cache (outside the autopkg org)."""
    try:
        repo = await add_custom_repo_to_cache(session, data.full_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    loaded = (
        await session.execute(
            select(GitHubRecipeRepo)
            .options(selectinload(GitHubRecipeRepo.cached_recipes))
            .where(GitHubRecipeRepo.id == repo.id)
        )
    ).scalar_one()
    return GitHubRecipeRepoRead.model_validate(loaded)


@router.delete("/cache/repos/{repo_owner}/{repo_name}")
async def remove_cached_github_repo(
    repo_owner: str,
    repo_name: str,
    session: AsyncSession = Depends(get_session),
):
    """Remove a repo from the discover cache (and its cached recipe index). Org repos reappear on Sync Repos."""
    try:
        full_name = normalize_github_full_name(f"{repo_owner}/{repo_name}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    ok = await remove_github_repo_from_cache(session, full_name)
    if not ok:
        raise HTTPException(status_code=404, detail="Repo not in cache")
    return {"removed": full_name}


@router.post("/recipes/add-override", response_model=AutoPkgRecipeRead)
async def add_recipe_override(
    data: AutoPkgRecipeCreate,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    """
    Add a discovered recipe as an override in the DB.
    Requires github_repo and recipe_path to fetch the actual recipe
    content and populate identifier, input_variables, trust_info, and parent_recipe.
    """
    if not data.github_repo or not data.recipe_path:
        raise HTTPException(
            status_code=400,
            detail="github_repo and recipe_path are required to create an override",
        )

    try:
        recipe_content = await fetch_recipe_content(data.github_repo, data.recipe_path)
    except GitHubRateLimitError:
        raise HTTPException(
            status_code=503,
            detail="GitHub API rate limit exceeded. Please try again later.",
        )
    except GitHubForbiddenError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub denied access: {exc.github_message or 'forbidden'}.",
        ) from None

    if not recipe_content:
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch recipe from GitHub: {data.github_repo}/{data.recipe_path}",
        )

    location_cache = await build_location_cache(session)

    try:
        override_info = await build_override_data(
            recipe_content,
            data.github_repo,
            data.recipe_path,
            location_cache=location_cache,
        )
    except GitHubRateLimitError:
        raise HTTPException(
            status_code=503,
            detail="GitHub API rate limit exceeded while building override. Please try again later.",
        )
    except GitHubForbiddenError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub denied access while building override: {exc.github_message or 'forbidden'}.",
        ) from None

    trust_info = override_info.get("trust_info", {})
    input_variables = override_info.get("input_variables", {})
    input_variables_for_db = _strip_pkginfo_from_input(input_variables if input_variables else None)

    override_plist = {
        "Identifier": override_info["identifier"],
        "ParentRecipe": override_info["parent_recipe"],
        "Input": input_variables or {},
    }
    override_plist["ParentRecipeTrustInfo"] = _plist_trust_snippet_from_db_trust(trust_info)

    payload = {
        "identifier": override_info["identifier"],
        "name": data.name,
        "parent_recipe": override_info["parent_recipe"],
        "input_variables": input_variables_for_db,
        "trust_info": trust_info,
        "override_data": override_plist,
        "source_repo_full_name": data.github_repo,
        "is_enabled": data.is_enabled,
        "auto_promote": data.auto_promote,
        "trust_status": "verified",
    }

    existing = await session.execute(select(AutoPkgRecipe).where(AutoPkgRecipe.identifier == payload["identifier"]))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Recipe override already exists")

    recipe = AutoPkgRecipe(**payload)
    session.add(recipe)

    audit_snapshot = {**payload}
    await create_audit_entry(
        session,
        action="create_override",
        entity_type="autopkg_recipe",
        entity_id=str(recipe.id),
        entity_name=recipe.name,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        after_snapshot=audit_snapshot,
    )

    await session.commit()
    await session.refresh(recipe)
    return AutoPkgRecipeRead.model_validate(recipe)


# ── Inferred repos ────────────────────────────────────────────────────────


@router.get("/repos/inferred")
async def list_inferred_repos(
    session: AsyncSession = Depends(get_session),
):
    """
    Return the set of GitHub repos needed for autopkg runs.
    Uses ``source_repo_full_name`` on each recipe when set,
    falling back to inference from ``trust_info`` for legacy recipes.
    """
    result = await session.execute(select(AutoPkgRecipe).where(AutoPkgRecipe.is_enabled.is_(True)))
    recipes = result.scalars().all()

    all_repos: set[str] = set()
    for recipe in recipes:
        if recipe.source_repo_full_name:
            all_repos.add(recipe.source_repo_full_name)
        elif recipe.trust_info:
            inferred = infer_repos_from_trust_info(recipe.trust_info)
            all_repos.update(inferred)

    return {
        "repos": sorted(all_repos),
        "total": len(all_repos),
        "recipe_count": len(recipes),
    }


@router.post("/results/{result_id}/approve")
async def approve_result(
    result_id: uuid.UUID,
    data: ApprovalRequest,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    result = await session.get(AutoPkgRunResult, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    if result.approval_status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail="Result is not pending approval")

    approved = data.approved
    if result.status == RecipeResultStatus.imported:
        pkg = await _resolve_pkg_for_pending_import_result(session, result)
        if pkg is not None and pkg.pending_catalog_names:
            if approved:
                before_catalogs = [c.name for c in pkg.catalogs]
                await session.execute(delete(PkgInfoCatalog).where(PkgInfoCatalog.pkg_info_id == pkg.id))
                await _assign_pkginfo_catalogs_by_name(session, pkg.id, list(pkg.pending_catalog_names))
                pkg.pending_catalog_names = None
                await session.flush()
                await session.refresh(pkg, attribute_names=["catalogs"])
                after_catalogs = [c.name for c in pkg.catalogs]
                await create_audit_entry(
                    session,
                    action="promote",
                    entity_type="pkg_info",
                    entity_id=str(pkg.id),
                    entity_name=f"{pkg.name} {pkg.version}",
                    user_id=user.id if user else None,
                    user_email=user.email if user else None,
                    before_snapshot={"catalogs": before_catalogs},
                    after_snapshot={"catalogs": after_catalogs},
                    notes="Released from quarantine after import approval",
                )
            else:
                before_catalogs = [c.name for c in pkg.catalogs]
                await session.execute(delete(PkgInfoCatalog).where(PkgInfoCatalog.pkg_info_id == pkg.id))
                pkg.pending_catalog_names = None
                pkg.is_deleted = True
                await create_audit_entry(
                    session,
                    action="reject",
                    entity_type="pkg_info",
                    entity_id=str(pkg.id),
                    entity_name=f"{pkg.name} {pkg.version}",
                    user_id=user.id if user else None,
                    user_email=user.email if user else None,
                    before_snapshot={"catalogs": before_catalogs, "is_deleted": False},
                    after_snapshot={"catalogs": [], "is_deleted": True},
                    notes="Import approval rejected; pkginfo marked deleted",
                )

    result.approval_status = ApprovalStatus.approved if approved else ApprovalStatus.rejected
    result.approved_by = user.email if user else "anonymous"
    result.approved_at = datetime.now(UTC)
    result.approval_comment = data.comment

    await create_audit_entry(
        session,
        action="approve" if approved else "reject",
        entity_type="autopkg_run_result",
        entity_id=str(result_id),
        entity_name=result.imported_display_name or result.recipe_name,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        notes=data.comment,
    )

    await session.commit()
    return {"message": "Approved" if approved else "Rejected"}


@router.get("/approvals", response_model=list[RunResultRead])
async def list_pending_approvals(
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(AutoPkgRunResult)
        .where(AutoPkgRunResult.approval_status == ApprovalStatus.pending)
        .order_by(AutoPkgRunResult.created_at.desc())
    )
    return [RunResultRead.model_validate(r) for r in result.scalars().all()]


# ── Metadata cache ───────────────────────────────────────────────────────


@router.get("/metadata-cache", response_model=MetadataCacheRead)
async def get_metadata_cache(
    workspace: str | None = Query(
        None,
        description=(
            "Runner workspace (e.g. ``/Users/runner/work/<owner>/<repo>`` or "
            "``/opt/UnitySrc/joncrain/munki-manager``) used to expand the "
            "``${WORKSPACE}`` placeholder in stored ``file_path`` entries. "
            "Defaults to ``GITHUB_WORKSPACE`` on the client when omitted; "
            "we leave the placeholder in place if not provided so the "
            "client-side rescue in load_metadata_cache.py can finish the job."
        ),
    ),
    session: AsyncSession = Depends(get_session),
):
    """Return the stored cloud-autopkg-runner metadata cache (one DB row per recipe).

    Stored ``file_path`` entries use a ``${WORKSPACE}`` placeholder so the
    same JSON is portable across runners (GitHub-hosted, Mac mini, dev Mac).
    Pass ``?workspace=...`` to expand the placeholder server-side; the
    runner script also expands client-side so unauth callers / older
    runners still get usable paths.
    """
    result = await session.execute(select(AutoPkgMetadataCacheEntry))
    rows = result.scalars().all()
    if not rows:
        return MetadataCacheRead(cache_data={}, updated_at=datetime.now(UTC))
    cache_data: dict = {}
    latest: datetime | None = None
    for r in rows:
        cache_data[r.recipe_key] = expand_cache_entry(r.entry, workspace) if workspace else r.entry
        if latest is None or r.updated_at > latest:
            latest = r.updated_at
    return MetadataCacheRead(cache_data=cache_data, updated_at=latest or datetime.now(UTC))


@router.put("/metadata-cache", response_model=MetadataCacheRead)
async def put_metadata_cache(
    data: MetadataCacheWrite,
    session: AsyncSession = Depends(get_session),
):
    """Replace the metadata cache from the runner's aggregated JSON (per-recipe rows in DB).

    Normalizes ``file_path`` entries to ``${WORKSPACE}/AutoPkg/Cache/...``
    on the way in so a Mac mini's ``/opt/UnitySrc/...`` paths and a
    GitHub-hosted runner's ``/Users/runner/work/.../...`` paths converge to
    the same canonical form in the DB. The next ``GET /metadata-cache``
    expands them back to whichever runner is asking.
    """
    await session.execute(delete(AutoPkgMetadataCacheEntry))
    now = datetime.now(UTC)
    normalized: dict = {}
    for key, entry in data.cache_data.items():
        if isinstance(entry, dict):
            clean = normalize_cache_entry(entry)
            session.add(AutoPkgMetadataCacheEntry(recipe_key=key, entry=clean, updated_at=now))
            normalized[key] = clean
    await session.commit()
    return MetadataCacheRead(cache_data=normalized, updated_at=now)


@router.delete("/metadata-cache")
async def delete_metadata_cache(
    recipe_key: str | None = Query(
        None,
        description="If set, delete only this recipe's cache key (e.g. AdobeReader.munki.recipe). "
        "Omit to clear the entire cache.",
    ),
    session: AsyncSession = Depends(get_session),
):
    """
    Remove cloud-autopkg-runner metadata cache entries.

    Stale entries cause **no_change** on the next run even after you delete a pkginfo:
    the runner still believes upstream matches the cached version. Clear the recipe's
    key (or the whole cache) before re-importing.
    """
    if recipe_key:
        result = await session.execute(
            delete(AutoPkgMetadataCacheEntry).where(AutoPkgMetadataCacheEntry.recipe_key == recipe_key)
        )
        deleted = result.rowcount or 0
        if deleted == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No metadata cache entry for recipe_key={recipe_key!r}",
            )
        await session.commit()
        return {"deleted": deleted, "recipe_key": recipe_key}

    result = await session.execute(delete(AutoPkgMetadataCacheEntry))
    deleted = result.rowcount or 0
    await session.commit()
    return {"deleted": deleted, "recipe_key": None}


# ── Pkginfo ingestion ────────────────────────────────────────────────────


async def _get_quarantine_catalog(session: AsyncSession) -> Catalog:
    result = await session.execute(select(Catalog).where(Catalog.is_quarantine.is_(True)))
    rows = result.scalars().all()
    if len(rows) != 1:
        raise HTTPException(
            status_code=422,
            detail="Designate exactly one quarantine catalog under Catalogs before importing "
            "with manual approval (recipe override with auto-promote off).",
        )
    return rows[0]


async def _assign_pkginfo_catalogs_by_name(
    session: AsyncSession,
    pkg_id: uuid.UUID,
    catalog_names: list[str],
) -> None:
    now = datetime.now(UTC)
    for cat_name in catalog_names:
        result = await session.execute(select(Catalog).where(Catalog.name == cat_name))
        catalog = result.scalar_one_or_none()
        if not catalog:
            catalog = Catalog(name=cat_name)
            session.add(catalog)
            await session.flush()
        session.add(
            PkgInfoCatalog(
                pkg_info_id=pkg_id,
                catalog_id=catalog.id,
                entered_at=now,
            )
        )
    await maybe_init_shard_after_catalog_change(session, pkg_id)


async def _resolve_pkg_for_pending_import_result(
    session: AsyncSession,
    result: AutoPkgRunResult,
) -> PkgInfo | None:
    if not result.imported_version:
        return None
    rec = (
        await session.execute(select(AutoPkgRecipe).where(AutoPkgRecipe.identifier == result.recipe_identifier))
    ).scalar_one_or_none()
    name_key = _recipe_pkginfo_key(rec) if rec else None
    base = await session.execute(
        select(PkgInfo).where(
            PkgInfo.version == result.imported_version,
            PkgInfo.is_deleted.is_(False),
            PkgInfo.pending_catalog_names.isnot(None),
        )
    )
    candidates = base.scalars().all()
    if name_key:
        for p in candidates:
            if p.name == name_key:
                return p
    if len(candidates) == 1:
        return candidates[0]
    return None


async def _pkginfo_promotion_fields_for_ingest(
    session: AsyncSession, recipe_row: AutoPkgRecipe | None
) -> tuple[bool, uuid.UUID | None]:
    if not recipe_row:
        return (False, None)
    wp = await session.get(WorkflowPreferences, 1)
    default_id = wp.default_promotion_channel_id if wp else None
    ch = recipe_row.promotion_channel_id or default_id
    return (bool(recipe_row.auto_promote), ch)


@router.post("/icons/ingest", response_model=IconUploadResponse)
async def ingest_icon_from_autopkg_runner(
    file: UploadFile = File(...),
    icon_name: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    """Store a runner-extracted PNG in ``software_icon`` (multipart, same semantics as ``/icons/upload``).

    Use this path from ``report_results.py`` with ``Authorization: Bearer <LOCAL_RUNNER_TOKEN>``;
    the route is also allowlisted for unauthenticated access when ``pkginfo/ingest`` is public
    (same network trust model).
    """
    raw = await file.read()
    stem = icon_name.strip()
    if not stem and file.filename:
        stem = file.filename.rsplit("/", 1)[-1]
        stem = stem.rsplit(".", 1)[0] if "." in stem else stem
    if not stem:
        raise HTTPException(
            status_code=422,
            detail="icon_name is required (or provide a filename on the upload)",
        )
    try:
        icon_stem, filename = await store_icon(session, stem, raw)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return IconUploadResponse(icon_name=icon_stem, filename=filename)


@router.post("/pkginfo/ingest")
async def ingest_pkginfo(
    data: PkgInfoIngest,
    session: AsyncSession = Depends(get_session),
):
    """Ingest a pkginfo plist dict from an AutoPkg run.

    When ``recipe_identifier`` resolves to a recipe row, the effective
    ``Input.pkginfo`` from the database is merged **on top of** the plist AutoPkg
    wrote: **merged** means ``override_data.Input`` combined with
    ``input_variables`` (override plist wins on conflicts; ``pkginfo`` dicts are
    deep-merged). That merged pkginfo overwrites AutoPkg output for every field
    except ``name`` / ``version``, which always come from the on-disk plist.

    **Quarantine:** Under *Catalogs*, exactly one catalog may be marked as the
    quarantine (holding) catalog. For **overrides** with **Auto-promote** off, new
    pkginfo is assigned **only** to that quarantine catalog until someone approves
    in the app; approval then moves it to the ``catalogs`` from the override. With
    **Auto-promote** on, pkginfo goes directly to the merged plist's ``catalogs``
    (no holding step). Parent (non-override) recipes use the merged plist's
    catalogs directly.

    Without a matching ``recipe_identifier``, the plist alone is used.
    """
    plist = data.pkginfo
    name = plist.get("name")
    version = plist.get("version")
    if not name or not version:
        raise HTTPException(status_code=422, detail="pkginfo must contain 'name' and 'version'")

    recipe_row: AutoPkgRecipe | None = None
    if data.recipe_identifier:
        r_row = await session.execute(select(AutoPkgRecipe).where(AutoPkgRecipe.identifier == data.recipe_identifier))
        recipe_row = r_row.scalar_one_or_none()

    merged_plist = dict(plist)
    if recipe_row is not None:
        ov = _get_override_pkginfo_dict(recipe_row)
        if ov is not None:
            merged_plist = _merge_plist_with_override_pkginfo(plist, ov)

    # ``installer_item_location`` stays as the relative path AutoPkg wrote into
    # the pkginfo. We used to overwrite it with ``AutoPkgRunResult.imported_pkg_url``
    # (the absolute storage URL) when a prior run at the same version existed,
    # but that turned out to be wrong on two counts:
    #   1. Some Munki client versions don't honor a bare-URL value here
    #      (the catalog/download path doesn't always exercise the URL
    #      short-circuit), so installs silently fail on repeat-version runs
    #      while first-run pkginfos worked.
    #   2. Even when Munki does honor it, baking the storage host into every
    #      pkginfo welds the deployment to that storage URL — changing CDN /
    #      container / base URL later means re-ingesting every pkginfo.
    #
    # The storage layout is already in lockstep with the plist (the runner
    # uploads to ``pkgs/<installer_item_location>`` — see
    # ``_post_multipart_upload_pkg`` in ``AutoPkg/scripts/report_results.py``),
    # so the relative path + ``MUNKI_REPO_PKG_BASE_URL`` is the canonical
    # resolver. ``AutoPkgRunResult.imported_pkg_url`` is still recorded for
    # audit / UI display but is no longer authoritative here.

    # catalog associations (from merged plist)
    raw_catalogs = merged_plist.get("catalogs", [])
    if isinstance(raw_catalogs, str):
        intended_catalog_names = [c.strip() for c in re.split(r"[,/|]+", raw_catalogs) if c.strip()]
    elif isinstance(raw_catalogs, list):
        intended_catalog_names = [str(x).strip() for x in raw_catalogs if str(x).strip()]
    else:
        intended_catalog_names = []

    # Override + not auto-promote: keep pkginfo in the designated quarantine catalog
    # until import approval promotes to ``intended_catalog_names`` (merged plist).
    use_quarantine = bool(recipe_row is not None and not recipe_row.auto_promote)
    quarantine_cat: Catalog | None = None
    if use_quarantine:
        quarantine_cat = await _get_quarantine_catalog(session)
    assign_catalog_names = [quarantine_cat.name] if use_quarantine and quarantine_cat else intended_catalog_names
    pending_catalog_names: list[str] | None = list(intended_catalog_names) if use_quarantine else None

    kwargs = _pkginfo_kwargs_from_plist(merged_plist)
    _apply_recipe_identifier_to_pkginfo_metadata(kwargs, data.recipe_identifier)

    existing_result = await session.execute(select(PkgInfo).where(PkgInfo.name == name, PkgInfo.version == version))
    existing_pkg = existing_result.scalar_one_or_none()
    if existing_pkg:
        was_deleted = existing_pkg.is_deleted
        if existing_pkg.is_deleted:
            existing_pkg.is_deleted = False
        _apply_pkginfo_kwargs_to_row(existing_pkg, kwargs)
        existing_pkg.pending_catalog_names = pending_catalog_names
        ap, ch = await _pkginfo_promotion_fields_for_ingest(session, recipe_row)
        existing_pkg.auto_promote = ap
        existing_pkg.promotion_channel_id = ch
        await session.execute(delete(PkgInfoCatalog).where(PkgInfoCatalog.pkg_info_id == existing_pkg.id))
        await _assign_pkginfo_catalogs_by_name(session, existing_pkg.id, assign_catalog_names)
        await session.flush()
        await session.commit()
        return {
            "message": "Already exists; updated from pkginfo + override"
            if not was_deleted
            else "Restored from delete and updated from pkginfo + override",
            "skipped": True,
            "revived": was_deleted,
            "catalogs_synced": True,
            "catalog_names": assign_catalog_names,
            "name": name,
            "version": version,
            "id": str(existing_pkg.id),
        }

    ap, ch = await _pkginfo_promotion_fields_for_ingest(session, recipe_row)
    pkg = PkgInfo(
        **kwargs,
        pending_catalog_names=pending_catalog_names,
        auto_promote=ap,
        promotion_channel_id=ch,
    )
    session.add(pkg)
    await session.flush()

    await _assign_pkginfo_catalogs_by_name(session, pkg.id, assign_catalog_names)

    await session.flush()
    await session.commit()
    return {
        "message": "Ingested",
        "skipped": False,
        "revived": False,
        "catalog_names": assign_catalog_names,
        "name": name,
        "version": version,
        "id": str(pkg.id),
    }
