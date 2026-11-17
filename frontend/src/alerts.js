import { useEffect, useState } from 'react'

import { api } from './api'

// #37: the counts behind the sidebar badges (pending friend requests and
// unread messages, plus requests you sent that were accepted). They refresh on
// navigation, every 30 seconds, when the student comes back to the tab, and
// whenever a page changes them (reading a conversation, answering a request).
export const ALERTS_REFRESH_MS = 30_000
export const ALERTS_CHANGED = 'semesterpilot:alerts-changed'
export const NO_ALERTS = { friend_requests: 0, unread_messages: 0 }

export function refreshAlerts() {
  window.dispatchEvent(new Event(ALERTS_CHANGED))
}

export function badgeText(count) {
  return count > 99 ? '99+' : String(count)
}

export function useAlerts(refreshKey) {
  const [alerts, setAlerts] = useState(NO_ALERTS)

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const data = await api('/social/alerts/')
        if (!active || !data) return
        setAlerts({
          friend_requests: Number(data.friend_requests) || 0,
          unread_messages: Number(data.unread_messages) || 0,
        })
      } catch {
        // A failed refresh leaves the badges as they were; the next one tries again.
      }
    }
    load()
    const timer = setInterval(load, ALERTS_REFRESH_MS)
    function whenVisible() {
      if (document.visibilityState === 'visible') load()
    }
    window.addEventListener(ALERTS_CHANGED, load)
    document.addEventListener('visibilitychange', whenVisible)
    return () => {
      active = false
      clearInterval(timer)
      window.removeEventListener(ALERTS_CHANGED, load)
      document.removeEventListener('visibilitychange', whenVisible)
    }
  }, [refreshKey])

  return alerts
}
