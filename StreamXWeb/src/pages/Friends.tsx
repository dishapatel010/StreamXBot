import { useEffect, useState } from 'react'
import { getFriends, getFriendRequests, sendFriendRequest, acceptFriendRequest, removeFriend, getFriendsListening } from '../services/friendsApi.js'

export const FriendsPage = () => {
    const [friends, setFriends] = useState<any[]>([])
    const [requests, setRequests] = useState<any[]>([])
    const [listening, setListening] = useState<any[]>([])
    const [loading, setLoading] = useState(false)
    const [toId, setToId] = useState<string>('')

    useEffect(() => {
        let mounted = true
        setLoading(true)
        Promise.all([getFriends().catch(() => ({ friends: [] })), getFriendRequests().catch(() => ({ requests: [] })), getFriendsListening().catch(() => ({ listening: [] }))])
            .then(([f, r, l]) => {
                if (!mounted) return
                setFriends(f.friends || [])
                setRequests(r.requests || [])
                setListening(l.listening || [])
            })
            .finally(() => { if (mounted) setLoading(false) })
        return () => { mounted = false }
    }, [])

    const handleSend = async (to: number) => { await sendFriendRequest(to); const r = await getFriendRequests(); setRequests(r.requests || []) }
    const handleAccept = async (userId: number) => { await acceptFriendRequest(userId); const f = await getFriends(); setFriends(f.friends || []) }
    const handleRemove = async (id: number) => { await removeFriend(id); const f = await getFriends(); setFriends(f.friends || []) }

    return (
        <div className="friends-page">
            <h1>Friends</h1>
            {loading ? <p>Loading...</p> : (
                <>
                    <section>
                        <h2>Requests</h2>
                        {requests.length === 0 ? <p>No requests</p> : (
                            <ul>{requests.map(r => (
                                <li key={r.user_id}>{r.first_name || r.username} <button onClick={() => handleAccept(r.user_id)}>Accept</button></li>
                            ))}</ul>
                        )}
                    </section>

                    <section>
                        <h2>Your Friends</h2>
                        {friends.length === 0 ? <p>No friends</p> : (
                            <ul>{friends.map(f => (
                                <li key={f._id}>{f.first_name || f.username} {f.presence?.online ? '(online)' : ''} <button onClick={() => handleRemove(f._id)}>Remove</button></li>
                            ))}</ul>
                        )}
                    </section>

                    <section>
                        <h2>Add Friend</h2>
                        <p>Send request by user id</p>
                        <input value={toId} onChange={(e) => setToId(e.target.value)} placeholder="User id" />
                        <button onClick={async () => { if (!toId) return; await handleSend(Number.parseInt(toId, 10)); setToId('') }}>Send Request</button>
                    </section>

                    <section>
                        <h2>Listening</h2>
                        {listening.length === 0 ? <p>No active listening</p> : (
                            <ul>{listening.map(l => <li key={l._id}>{l.user_id} - {l.track_id} {l.is_playing ? '(playing)' : ''}</li>)}</ul>
                        )}
                    </section>
                </>
            )}
        </div>
    )
}
