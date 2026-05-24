import { useEffect } from 'react'
import { documentTitle } from '@/lib/document-title'

export function useDocumentTitle(
  ...parts: (string | null | undefined | false)[]
) {
  const title = documentTitle(...parts)
  useEffect(() => {
    document.title = title
  }, [title])
}
