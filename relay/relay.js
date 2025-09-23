import http from 'node:http'
import Redis from 'ioredis'

const REDIS_URL = process.env.CEDARPY_REDIS_URL || 'redis://127.0.0.1:6379/0'
const PORT = parseInt(process.env.CEDAR_RELAY_PORT || process.env.PORT || '8808', 10)
const HOST = process.env.CEDAR_RELAY_HOST || '127.0.0.1'
const CORS = process.env.CEDAR_RELAY_CORS || '*'

function sseHeaders(res) {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Access-Control-Allow-Origin': CORS,
  })
  res.write(':ok\n\n')
}

const server = http.createServer(async (req, res) => {
  if (!req.url) { res.statusCode = 404; return res.end('not found') }
  const m = req.url.match(/^\/sse\/(\d+)/)
  if (!m) { res.statusCode = 404; return res.end('not found') }
  const threadId = m[1]
  sseHeaders(res)
  const sub = new Redis(REDIS_URL)
  const chan = `cedar:thread:${threadId}:pub`
  await sub.subscribe(chan)
  const keepAlive = setInterval(() => { try { res.write(':ka\n\n') } catch(e){} }, 20000)
  sub.on('message', (_ch, msg) => {
    try { res.write(`data: ${msg}\n\n`) } catch (e) {}
  })
  req.on('close', () => {
    clearInterval(keepAlive)
    try { sub.disconnect() } catch (_) {}
  })
})

server.listen(PORT, HOST, () => {
  console.log(`[relay] listening on http://${HOST}:${PORT} (redis: ${REDIS_URL})`)
})
