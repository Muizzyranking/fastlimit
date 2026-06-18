-- token_bucket.lua
--
-- Atomic token bucket using a hash to store (tokens, last_refill_ms).
-- Tokens refill continuously at rate = limit / window_ms.
-- Allows bursting up to `limit` tokens.
--
-- KEYS[1]   = bucket key
--
-- ARGV[1]   = now_ms
-- ARGV[2]   = window_ms    (full refill period in ms, derived from window_sec)
-- ARGV[3]   = limit        (bucket capacity = max burst)
-- ARGV[4]   = cost
--
-- Returns: { allowed, retry_after_ms, reset_ms, remaining, limit }

local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local data = redis.call("HMGET", key, "tokens", "last_refill_ms")
local tokens = tonumber(data[1] or limit)
local last_refill = tonumber(data[2] or now_ms)

-- refill tokens proportional to elapsed time
local elapsed = math.max(now_ms - last_refill, 0)
local refill = (elapsed / window_ms) * limit
tokens = math.min(tokens + refill, limit)

if tokens < cost then
	-- time until enough tokens accumulate
	local needed_ms = ((cost - tokens) / limit) * window_ms
	local reset_ms = now_ms + math.ceil(needed_ms)
	return { 0, math.max(math.ceil(needed_ms), 1000), reset_ms, 0, limit }
end

tokens = tokens - cost
local reset_ms = now_ms + math.ceil(((limit - tokens) / limit) * window_ms)

redis.call("HMSET", key, "tokens", tokens, "last_refill_ms", now_ms)
redis.call("PEXPIRE", key, window_ms + 1000)

local remaining = math.floor(tokens)
return { 1, 0, reset_ms, remaining, limit }
