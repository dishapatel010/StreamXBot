import { API_BASE_URL, getAuthToken } from './api.js'

async function authFetch(path: string, method = 'GET', body: unknown = null) {
    const token = getAuthToken()
    if (!token) throw new Error('Not authenticated')

    const opts: RequestInit = {
        method,
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
    }
    if (body) opts.body = JSON.stringify(body)

    const res = await fetch(`${API_BASE_URL}${path}`, opts)
    if (!res.ok) {
        const txt = await res.text().catch(() => '')
        throw new Error(`API ${res.status}: ${txt}`)
    }
    return res.json()
}

export async function getFriends() {
    return authFetch('/friends')
}

export async function getFriendRequests() {
    return authFetch('/friends/requests')
}

export async function sendFriendRequest(to: number) {
    return authFetch('/friends/request', 'POST', { to })
}

export async function acceptFriendRequest(userId: number) {
    return authFetch('/friends/accept', 'POST', { userId })
}

export async function removeFriend(friendId: number) {
    return authFetch(`/friends/${friendId}`, 'DELETE')
}

export async function getFriendsListening() {
    return authFetch('/friends/listening')
}
