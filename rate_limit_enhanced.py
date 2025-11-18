# core/rate_limit_enhanced.py
"""
Enhanced rate limiting system for Gemini API with smart key scheduling.

Features:
- Intelligent wait time calculation based on number of keys
- Per-key tracking with penalties and cooldowns
- More keys = less waiting time per key
- Automatic penalty decay on successful requests
- Thread-safe operation
"""

import time
import threading
import logging
from typing import List, Optional, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class KeyMetrics:
    last_used: float = 0.0
    penalty: float = 1.0
    success_count: int = 0
    fail_count: int = 0
    total_requests: int = 0
    daily_quota_hit: bool = False   # ⭐ NEW

    def reset_stats(self):
        """Reset statistics but keep penalty."""
        self.success_count = 0
        self.fail_count = 0
        self.total_requests = 0


class SmartRateLimiter:
    """
    Smart rate limiter with dynamic wait time calculation.
    
    Key Formula:
        wait_time = (60 / RPM) * penalty / num_keys
    
    This means:
    - 1 key: full wait time
    - 2 keys: half wait time per key
    - 4 keys: quarter wait time per key
    """
    
    def __init__(self, base_rpm: int = 15):
        """
        Initialize rate limiter.
        
        Args:
            base_rpm: Requests per minute per key (Gemini Pro default: 15 RPM)
        """
        self.base_rpm = base_rpm
        self.lock = threading.RLock()
        self.key_metrics: Dict[str, KeyMetrics] = {}
        
        # Penalty settings
        self.penalty_increment = 2.0  # Multiply penalty by this on failure
        self.penalty_decay = 0.85     # Multiply penalty by this on success
        self.max_penalty = 30.0       # Maximum penalty multiplier
        self.min_penalty = 1.0        # Minimum penalty (normal speed)
        
        logger.info(f"SmartRateLimiter initialized: {base_rpm} RPM base")
        
    def all_keys_daily_exhausted(self, keys):
        """Returns True if ALL keys have hit daily quota."""
        with self.lock:
            for k in keys:
                if k not in self.key_metrics:
                    return False
                if not self.key_metrics[k].daily_quota_hit:
                    return False
            return True
    
    def _ensure_key(self, key: str):
        """Ensure key exists in metrics."""
        if key not in self.key_metrics:
            self.key_metrics[key] = KeyMetrics()
    
    def calculate_wait_time(self, key: str, total_keys: int) -> float:
        """
        Calculate wait time for a specific key.
        
        Args:
            key: API key
            total_keys: Total number of available keys
        
        Returns:
            Wait time in seconds
        """
        with self.lock:
            self._ensure_key(key)
            metrics = self.key_metrics[key]
            
            # Base interval per key (in seconds)
            base_interval = 60.0 / self.base_rpm
            
            # Scale by number of keys (more keys = less wait per key)
            key_scaling = 1.0 / max(1, total_keys)
            
            # Apply penalty
            wait_time = base_interval * key_scaling * metrics.penalty
            
            return wait_time
    
    def get_ready_time(self, key: str, total_keys: int) -> float:
        """
        Get timestamp when key will be ready.
        
        Args:
            key: API key
            total_keys: Total number of keys
        
        Returns:
            Timestamp when key is ready (time.time() format)
        """
        with self.lock:
            self._ensure_key(key)
            metrics = self.key_metrics[key]
            wait_time = self.calculate_wait_time(key, total_keys)
            return metrics.last_used + wait_time
    
    def select_best_key(self, keys: List[str], max_wait: float = 30.0) -> tuple[str, float]:
        """
        Select the best available key, waiting if necessary.
        
        Args:
            keys: List of available API keys
            max_wait: Maximum time to wait (seconds)
        
        Returns:
            Tuple of (selected_key, wait_time)
        """
        if not keys:
            raise ValueError("No API keys available")
        
        # Deduplicate keys while preserving order
        unique_keys = list(dict.fromkeys(keys))
        total_keys = len(unique_keys)
        
        start_time = time.time()
        
        with self.lock:
            # Initialize all keys
            for key in unique_keys:
                self._ensure_key(key)
            
            while True:
                now = time.time()
                elapsed = now - start_time
                
                # Check if we've exceeded max wait
                if elapsed >= max_wait:
                    # Return least penalized key immediately
                    best_key = min(
                        unique_keys,
                        key=lambda k: self.key_metrics[k].penalty
                    )
                    logger.warning(
                        f"⏱️ Max wait exceeded ({max_wait}s), using key with "
                        f"penalty {self.key_metrics[best_key].penalty:.1f}"
                    )
                    return best_key, elapsed
                
                # Find keys that are ready now
                ready_keys = []
                for key in unique_keys:
                    ready_time = self.get_ready_time(key, total_keys)
                    if ready_time <= now:
                        ready_keys.append((key, ready_time))
                
                if ready_keys:
                    # Pick the key that's been ready the longest (most rested)
                    best_key, _ = min(ready_keys, key=lambda x: x[1])
                    
                    logger.info(
                        f"✅ Selected key {best_key[:8]}... "
                        f"(penalty: {self.key_metrics[best_key].penalty:.1f}x, "
                        f"total keys: {total_keys})"
                    )
                    return best_key, elapsed
                
                # No keys ready, find soonest available
                soonest_key = min(
                    unique_keys,
                    key=lambda k: self.get_ready_time(k, total_keys)
                )
                soonest_time = self.get_ready_time(soonest_key, total_keys)
                wait_needed = soonest_time - now
                
                # Check if we can wait
                if elapsed + wait_needed > max_wait:
                    # Would exceed max_wait, return best key now
                    logger.warning("⚠️ Would exceed max_wait, returning best key now")
                    return soonest_key, elapsed
                
                # Wait for soonest key (capped at 1 second per iteration)
                sleep_time = min(wait_needed, 1.0)
                
                logger.debug(
                    f"⏳ Waiting {sleep_time:.2f}s for key {soonest_key[:8]}... "
                    f"(ready in {wait_needed:.2f}s)"
                )
                
                # Release lock during sleep
                self.lock.release()
                time.sleep(sleep_time)
                self.lock.acquire()
    
    def mark_used(self, key: str):
        """Mark key as used (updates timestamp)."""
        with self.lock:
            self._ensure_key(key)
            self.key_metrics[key].last_used = time.time()
            self.key_metrics[key].total_requests += 1
    
    def mark_success(self, key: str):
        """Mark successful request (decay penalty)."""
        with self.lock:
            self._ensure_key(key)
            metrics = self.key_metrics[key]
            
            metrics.success_count += 1
            
            # Decay penalty on success
            new_penalty = max(
                self.min_penalty,
                metrics.penalty * self.penalty_decay
            )
            
            if new_penalty != metrics.penalty:
                logger.info(
                    f"✨ Key {key[:8]}... penalty reduced: "
                    f"{metrics.penalty:.1f}x → {new_penalty:.1f}x"
                )
            
            metrics.penalty = new_penalty
    
    def mark_failure(self, key: str, is_rate_limit: bool = True):
        with self.lock:
            self._ensure_key(key)
            metrics = self.key_metrics[key]

            metrics.fail_count += 1

            if is_rate_limit:
                # Mark daily quota hit (strict)
                metrics.daily_quota_hit = True

                # Increase penalty
                new_penalty = min(self.max_penalty, metrics.penalty * self.penalty_increment)
                logger.warning(
                    f"⚠️ Key {key[:8]}... rate limited! "
                    f"Penalty: {metrics.penalty:.1f}x → {new_penalty:.1f}x"
                )
                metrics.penalty = new_penalty
            else:
                logger.error(f"❌ Key {key[:8]}... request failed (non-rate-limit)")

    
    def get_status(self) -> dict:
        """Get status of all keys."""
        with self.lock:
            return {
                key[:8] + "...": {
                    "penalty": f"{m.penalty:.1f}x",
                    "success": m.success_count,
                    "fail": m.fail_count,
                    "total": m.total_requests,
                    "last_used": f"{time.time() - m.last_used:.1f}s ago"
                }
                for key, m in self.key_metrics.items()
            }
    
    def reset_key(self, key: str):
        """Reset a specific key's metrics."""
        with self.lock:
            if key in self.key_metrics:
                self.key_metrics[key] = KeyMetrics()
                logger.info(f"🔄 Reset metrics for key {key[:8]}...")
    
    def reset_all(self):
        """Reset all keys."""
        with self.lock:
            self.key_metrics.clear()
            logger.info("🔄 Reset all key metrics")


# Global instance
_limiter: Optional[SmartRateLimiter] = None


def get_limiter() -> SmartRateLimiter:
    """Get or create global rate limiter."""
    global _limiter
    if _limiter is None:
        _limiter = SmartRateLimiter(base_rpm=15)  # Gemini Pro: 15 RPM
    return _limiter


def configure_limiter(base_rpm: int):
    """Configure rate limiter settings."""
    global _limiter
    _limiter = SmartRateLimiter(base_rpm=base_rpm)
    logger.info(f"Configured rate limiter: {base_rpm} RPM")


# =====================================================================
# INTEGRATION WITH OPTIMIZED GEMINI CLIENT
# =====================================================================

def get_next_api_key_with_limiter() -> Optional[str]:
    """
    Get next API key with intelligent rate limiting.
    Replacement for the simple round-robin in optimized_gemini_client.py
    """
    from utils.config import load_config
    
    cfg = load_config()
    all_keys = cfg.get("gemini_api_keys", [])
    
    if not all_keys:
        logger.error("❌ No Gemini API keys found in config.")
        return None
    
    # Get rate limiter
    limiter = get_limiter()
    
    try:
        # Select best key (will wait if needed)
        key, wait_time = limiter.select_best_key(all_keys, max_wait=30.0)
        
        if wait_time > 0.1:
            logger.info(f"⏱️ Waited {wait_time:.2f}s for available key")
        
        # Mark as used
        limiter.mark_used(key)
        
        return key
        
    except Exception as e:
        logger.error(f"Failed to get API key: {e}")
        return all_keys[0] if all_keys else None


# =====================================================================
# EXAMPLE USAGE
# =====================================================================

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Initialize limiter (15 RPM = typical Gemini Pro limit)
    limiter = get_limiter()
    
    # Simulate keys
    keys = ["key1_abc", "key2_def", "key3_ghi", "key4_jkl"]
    
    print("\n" + "=" * 70)
    print("SMART RATE LIMITER DEMONSTRATION")
    print("=" * 70)
    
    print(f"\n📊 Configuration:")
    print(f"   Base RPM per key: {limiter.base_rpm}")
    print(f"   Total keys: {len(keys)}")
    print(f"   Effective wait per key: {60/limiter.base_rpm/len(keys):.2f}s")
    print(f"   Theoretical throughput: {limiter.base_rpm * len(keys)} RPM")
    
    # Simulate burst of requests
    print(f"\n🔥 Simulating 15 rapid requests...")
    
    for i in range(15):
        print(f"\n--- Request {i+1}/15 ---")
        
        # Select best key (with automatic waiting)
        key, wait_time = limiter.select_best_key(keys, max_wait=10.0)
        
        # Mark as used
        limiter.mark_used(key)
        
        # Simulate API call result
        if i in [5, 11]:  # Simulate rate limits on requests 6 and 12
            limiter.mark_failure(key, is_rate_limit=True)
            print(f"❌ Rate limited! Key {key[:8]}... penalized")
        else:
            limiter.mark_success(key)
            print(f"✅ Success with key {key[:8]}...")
        
        # Small delay to simulate processing
        time.sleep(0.05)
    
    # Show final status
    print(f"\n" + "=" * 70)
    print("📈 Final Key Statistics:")
    print("=" * 70)
    
    status = limiter.get_status()
    for key_display, stats in status.items():
        print(f"\n{key_display}:")
        for k, v in stats.items():
            print(f"  {k:12}: {v}")
    
    print("\n" + "=" * 70)
    
    # Show scaling demonstration
    print("\n💡 Scaling Benefits:")
    for n in [1, 2, 4, 8]:
        wait = 60 / limiter.base_rpm / n
        throughput = limiter.base_rpm * n
        print(f"   {n} key{'s' if n > 1 else ' '}: "
              f"{wait:.2f}s wait/key, {throughput} RPM total")
    
    print("\n" + "=" * 70 + "\n")