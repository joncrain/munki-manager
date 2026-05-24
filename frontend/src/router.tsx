import { createBrowserRouter, Navigate } from 'react-router-dom'
import { RouteErrorBoundary } from '@/components/route-error-boundary'
import RootLayout from '@/root-layout'

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    // Catches errors anywhere in the route tree, including lazy() chunk-load
    // failures after a redeploy invalidates the user's cached index.html.
    errorElement: <RouteErrorBoundary />,
    children: [
      {
        index: true,
        lazy: () =>
          import('@/app/page').then((m) => ({ Component: m.default })),
      },
      {
        path: 'login',
        lazy: () =>
          import('@/app/login/page').then((m) => ({ Component: m.default })),
      },
      {
        path: 'register',
        lazy: () =>
          import('@/app/register/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'auth/callback',
        lazy: () =>
          import('@/app/auth/callback/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'enroll',
        lazy: () =>
          import('@/app/enroll/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'settings',
        lazy: () =>
          import('@/app/settings/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'settings/account',
        element: <Navigate to="/settings" replace />,
      },
      {
        path: 'software',
        lazy: () =>
          import('@/app/software/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'software/:id',
        lazy: () =>
          import('@/app/software/[id]/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'manifests',
        lazy: () =>
          import('@/app/manifests/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'manifests/:id',
        lazy: () =>
          import('@/app/manifests/[id]/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'catalogs',
        lazy: () =>
          import('@/app/catalogs/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'reporting',
        lazy: () =>
          import('@/app/reporting/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'reporting/installs',
        lazy: () =>
          import('@/app/reporting/installs/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'reporting/devices/:id',
        lazy: () =>
          import('@/app/reporting/devices/[id]/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'autopkg/recipes',
        lazy: () =>
          import('@/app/autopkg/recipes/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'autopkg/recipes/:id',
        lazy: () =>
          import('@/app/autopkg/recipes/[id]/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'autopkg/runs',
        lazy: () =>
          import('@/app/autopkg/runs/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'autopkg/schedules',
        lazy: () =>
          import('@/app/autopkg/schedules/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'autopkg/discover',
        lazy: () =>
          import('@/app/autopkg/discover/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'audit',
        lazy: () =>
          import('@/app/audit/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'approvals',
        lazy: () =>
          import('@/app/approvals/page').then((m) => ({
            Component: m.default,
          })),
      },
      {
        path: 'admin/access',
        lazy: () =>
          import('@/app/admin/access/page').then((m) => ({
            Component: m.default,
          })),
      },
    ],
  },
])
