import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { toast } from 'sonner'
import { type AutoPkgRunRead, api } from '@/lib/api'
import {
  type RecipeQuickRunTarget,
  toastLocalRunRegistered,
  type VerifyTrustForRunResponse,
  verifyTrustBeforeRun,
} from '@/lib/autopkg-run'

type TrustIssue = {
  runner: 'github' | 'local'
  verify: VerifyTrustForRunResponse
}

/**
 * Create AutoPkg run (GitHub or local) with the same trust verification + dialogs as the recipes list.
 */
export function useAutopkgQuickRun(options?: { onRunSuccess?: () => void }) {
  const onRunSuccess = options?.onRunSuccess
  const queryClient = useQueryClient()
  const [quickRun, setQuickRun] = useState<RecipeQuickRunTarget | null>(null)
  const [trustVerifyIssue, setTrustVerifyIssue] = useState<null | TrustIssue>(
    null,
  )
  const [trustVerifying, setTrustVerifying] = useState(false)
  const [trustContinuePending, setTrustContinuePending] = useState(false)

  const triggerRunMutation = useMutation({
    mutationFn: (args: {
      recipeNames: string[] | null
      runner: 'github' | 'local'
    }) =>
      api.post<AutoPkgRunRead>('/autopkg/runs', {
        recipe_names: args.recipeNames,
        runner: args.runner,
      }),
    onSuccess: (run) => {
      onRunSuccess?.()
      if (run.runner_type === 'local') {
        toastLocalRunRegistered(run)
      } else {
        toast.success('AutoPkg run triggered on GitHub Actions', {
          description: `Run ID: ${run.id}`,
          duration: 15_000,
        })
      }
      void queryClient.invalidateQueries({ queryKey: ['autopkg-runs'] })
      void queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
      void queryClient.invalidateQueries({
        queryKey: ['autopkg-recipes-enabled'],
      })
      void queryClient.invalidateQueries({ queryKey: ['autopkg-recipe'] })
    },
    onError: (err: Error) =>
      toast.error(`Failed to trigger run: ${err.message}`),
  })

  const onQuickRunConfirm = useCallback(
    async (runner: 'github' | 'local', recipeNames: string[] | null) => {
      const toastId = toast.loading('Verifying trust with GitHub…')
      setTrustVerifying(true)
      try {
        const res = await verifyTrustBeforeRun(recipeNames)
        if (res.rate_limited && res.results.length === 0) {
          toast.error(
            'GitHub rate limit while verifying trust. Try again later.',
          )
          return
        }
        const failed = res.results.filter((r) => r.status !== 'verified')
        await queryClient.invalidateQueries({ queryKey: ['autopkg-recipes'] })
        await queryClient.invalidateQueries({
          queryKey: ['autopkg-recipes-enabled'],
        })
        await queryClient.invalidateQueries({
          queryKey: ['pending-trust-changes-count'],
        })
        await queryClient.invalidateQueries({
          queryKey: ['pending-trust-changes'],
        })
        if (failed.length === 0) {
          triggerRunMutation.mutate({ recipeNames, runner })
          return
        }
        setTrustVerifyIssue({ runner, verify: res })
      } catch (e) {
        toast.error(
          e instanceof Error ? e.message : 'Trust verification failed',
        )
      } finally {
        toast.dismiss(toastId)
        setTrustVerifying(false)
      }
    },
    [queryClient, triggerRunMutation],
  )

  const onTrustDialogContinue = useCallback(() => {
    if (!trustVerifyIssue) return
    const names = trustVerifyIssue.verify.results
      .filter((r) => r.status === 'verified')
      .map((r) => r.name)
    if (names.length === 0) {
      toast.error('No recipes left to run after trust check')
      setTrustVerifyIssue(null)
      return
    }
    setTrustContinuePending(true)
    triggerRunMutation.mutate(
      { recipeNames: names, runner: trustVerifyIssue.runner },
      {
        onSettled: () => {
          setTrustContinuePending(false)
          setTrustVerifyIssue(null)
        },
      },
    )
  }, [trustVerifyIssue, triggerRunMutation])

  const runActionPending = triggerRunMutation.isPending || trustVerifying

  return {
    quickRun,
    setQuickRun,
    runActionPending,
    trustVerifying,
    trustVerifyIssue,
    setTrustVerifyIssue,
    trustContinuePending,
    onQuickRunConfirm,
    onTrustDialogStop: () => setTrustVerifyIssue(null),
    onTrustDialogContinue,
    triggerRunMutation,
  }
}
