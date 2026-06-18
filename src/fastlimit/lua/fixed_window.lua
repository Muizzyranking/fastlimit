-- fixed_window.lua
--
-- Atomic fixed window rate limiter using a simple counter + TTL.
-- Simpler and cheaper than sliding window but allows 2x burst at window edges.
--
-- KEYS[1]   = bucket key
--
-- ARGV[1]   = now_ms
-- ARGV[2]   = window_sec   (window size in seconds)
-- ARGV[3]   = limit
-- ARGV[4]   = cost
--
-- Returns: { allowed, retry_after_ms, reset_ms, remaining, limit }

local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_sec = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

-- fixed window boundary: floor(now / window) * window
local window_ms = window_sec * 1000
local window_start = math.floor(now_ms / window_ms) * window_ms
local reset_ms = window_start + window_ms

local count = tonumber(redis.call("GET", key) or "0")

if count + cost > limit then
	local retry_ms = reset_ms - now_ms
	return { 0, math.max(retry_ms, 1000), reset_ms, 0, limit }
end

local new_count = redis.call("INCRBY", key, cost)
if new_count == cost then
	-- first request in this window — set TTL
	redis.call("EXPIRE", key, window_sec + 1)
end

local remaining = limit - new_count
return { 1, 0, reset_ms, remaining, limit }
