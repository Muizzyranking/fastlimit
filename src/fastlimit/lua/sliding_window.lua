-- sliding_window.lua
--
-- Atomic sliding window rate limiter using a sorted set.
--
-- KEYS[1]   = bucket key (e.g. "fastlimit:rl:login:ip:1.2.3.4")
--
-- ARGV[1]   = now_ms       (current Unix timestamp in milliseconds)
-- ARGV[2]   = window_ms    (window size in milliseconds)
-- ARGV[3]   = limit        (max requests allowed in window)
-- ARGV[4]   = cost         (how many slots this request consumes)
-- ARGV[5]   = member       (unique token for this request, e.g. random hex)
--
-- Returns: { allowed, retry_after_ms, reset_ms, remaining, limit }

local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local member = ARGV[5]
local cutoff_ms = now_ms - window_ms

-- evict expired entries
redis.call("ZREMRANGEBYSCORE", key, "-inf", cutoff_ms)

local count = redis.call("ZCARD", key)

if count + cost > limit then
	local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
	local oldest_ms = oldest[2] and tonumber(oldest[2]) or now_ms
	local retry_ms = math.max((oldest_ms + window_ms) - now_ms, 1000)
	return { 0, retry_ms, oldest_ms + window_ms, 0, limit }
end

-- record cost entries with unique members to avoid collisions
for i = 1, cost do
	redis.call("ZADD", key, now_ms, member .. ":" .. i)
end
redis.call("EXPIRE", key, math.ceil(window_ms / 1000) + 1)

local remaining = limit - (count + cost)
local reset_ms = now_ms + window_ms

return { 1, 0, reset_ms, remaining, limit }
