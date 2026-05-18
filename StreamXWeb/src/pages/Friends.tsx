import { useEffect, useState } from 'react'
import { getFriends, getFriendRequests, sendFriendRequest, acceptFriendRequest, removeFriend, getFriendsListening } from '../services/friendsApi.js'
import './Friends.css'

type FriendItem = {
    _id: number
    first_name?: string
    username?: string
    presence?: { online?: boolean }
}

type FriendRequestItem = {
    user_id: number
    first_name?: string
    username?: string
}

type ListeningItem = {
    _id: string
    user_id: number
    track_id: string
    is_playing?: boolean
}

export const FriendsPage = () => {
    const [friends, setFriends] = useState<FriendItem[]>([])
    const [requests, setRequests] = useState<FriendRequestItem[]>([])
    const [listening, setListening] = useState<ListeningItem[]>([])
    const [loading, setLoading] = useState(false)
    const [toId, setToId] = useState<string>('')
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        let mounted = true
        setLoading(true)
        setError(null)

        Promise.all([
            getFriends().catch(() => ({ friends: [] })),
            getFriendRequests().catch(() => ({ requests: [] })),
            getFriendsListening().catch(() => ({ listening: [] })),
        ])
            .then(([friendsRes, requestsRes, listeningRes]) => {
                if (!mounted) return
                setFriends((friendsRes.friends || []) as FriendItem[])
                setRequests((requestsRes.requests || []) as FriendRequestItem[])
                setListening((listeningRes.listening || []) as ListeningItem[])
            })
            .catch(() => {
                if (!mounted) return
                setError('Failed loading friends')
            })
            .finally(() => {
                if (mounted) setLoading(false)
            })

        return () => {
            mounted = false
        }
    }, [])

    const handleSend = async (to: number) => {
        await sendFriendRequest(to)
        const requestsRes = await getFriendRequests()
        setRequests((requestsRes.requests || []) as FriendRequestItem[])
    }

    const handleAccept = async (userId: number) => {
        await acceptFriendRequest(userId)
        const [friendsRes, requestsRes] = await Promise.all([getFriends(), getFriendRequests()])
        setFriends((friendsRes.friends || []) as FriendItem[])
        setRequests((requestsRes.requests || []) as FriendRequestItem[])
    }

    const handleRemove = async (id: number) => {
        await removeFriend(id)
        const friendsRes = await getFriends()
        setFriends((friendsRes.friends || []) as FriendItem[])
    }

    const submitAddFriend = async () => {
        const parsed = Number.parseInt(toId, 10)
        if (!Number.isFinite(parsed) || parsed <= 0) {
            setError('Enter valid user id')
            return
        }

        try {
            setError(null)
            await handleSend(parsed)
            setToId('')
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Send request failed')
        }
    }

    return (
        <div className="friends-page">
            <div className="friends-page-content">
                <h1 className="friends-page-title">Friends</h1>

                {loading ? <p className="friends-muted">Loading...</p> : null}
                {error ? <p className="friends-error">{error}</p> : null}

                <section className="friends-card">
                    <h2 className="friends-card-title">Add Friend</h2>
                    <p className="friends-muted">Send request by user id</p>
                    <div className="friends-inline-form">
                        <input
                            className="friends-input"
                            value={toId}
                            onChange={(e) => setToId(e.target.value)}
                            placeholder="User id"
                        />
                        <button className="friends-btn" onClick={submitAddFriend}>Send Request</button>
                    </div>
                </section>

                <section className="friends-card">
                    <h2 className="friends-card-title">Requests</h2>
                    {requests.length === 0 ? (
                        <p className="friends-muted">No requests</p>
                    ) : (
                        <ul className="friends-list">
                            {requests.map((request) => (
                                <li className="friends-list-item" key={request.user_id}>
                                    <span className="friends-name">{request.first_name || request.username || request.user_id}</span>
                                    <button className="friends-btn" onClick={() => handleAccept(request.user_id)}>Accept</button>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>

                <section className="friends-card">
                    <h2 className="friends-card-title">Your Friends</h2>
                    {friends.length === 0 ? (
                        <p className="friends-muted">No friends</p>
                    ) : (
                        <ul className="friends-list">
                            {friends.map((friend) => (
                                <li className="friends-list-item" key={friend._id}>
                                    <span className="friends-name">
                                        {friend.first_name || friend.username || friend._id}
                                        {friend.presence?.online ? <span className="friends-online"> online</span> : null}
                                    </span>
                                    <button className="friends-btn friends-btn-danger" onClick={() => handleRemove(friend._id)}>Remove</button>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>

                <section className="friends-card">
                    <h2 className="friends-card-title">Listening</h2>
                    {listening.length === 0 ? (
                        <p className="friends-muted">No active listening</p>
                    ) : (
                        <ul className="friends-list">
                            {listening.map((item) => (
                                <li className="friends-list-item" key={item._id}>
                                    <span className="friends-name">{item.user_id} - {item.track_id}</span>
                                    <span className="friends-muted">{item.is_playing ? 'playing' : 'paused'}</span>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>
            </div>
        </div>
    )
}
