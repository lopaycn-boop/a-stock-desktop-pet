"""Enhanced cycle execution with timeout protection and validation."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("potato")


class CycleTimeout(Exception):
    """Raised when cycle execution exceeds max duration."""
    pass


class CycleValidationError(Exception):
    """Raised when cycle validation fails."""
    pass


@contextmanager
def cycle_timeout(max_seconds: float = 120):
    """Context manager for cycle timeout protection.
    
    Args:
        max_seconds: Maximum allowed execution time in seconds.
        
    Raises:
        CycleTimeout: If execution exceeds max_seconds.
    """
    start_time = time.time()
    
    def timeout_handler():
        elapsed = time.time() - start_time
        if elapsed > max_seconds:
            raise CycleTimeout(
                f"Cycle execution exceeded {max_seconds}s (elapsed: {elapsed:.2f}s)"
            )
    
    try:
        yield timeout_handler
    finally:
        elapsed = time.time() - start_time
        if elapsed > max_seconds:
            logger.error(
                "Cycle execution exceeded timeout",
                extra={
                    "elapsed_seconds": elapsed,
                    "max_seconds": max_seconds,
                    "overage_seconds": elapsed - max_seconds,
                }
            )


def validate_cycle_prerequisites(settings: Any, db: Any) -> dict[str, Any]:
    """Validate that all prerequisites for cycle execution are met.
    
    Args:
        settings: Application settings.
        db: Database instance.
        
    Returns:
        Validation result dictionary.
        
    Raises:
        CycleValidationError: If validation fails critically.
    """
    validation_result = {
        "ok": True,
        "warnings": [],
        "errors": [],
        "checks": {},
    }
    
    # Check 1: Database connectivity
    state = {}
    try:
        state = db.get_risk_state()
        validation_result["checks"]["database"] = "ok"
        logger.info("Database connectivity: OK")
    except Exception as exc:
        msg = f"Database connectivity failed: {exc}"
        validation_result["errors"].append(msg)
        validation_result["checks"]["database"] = "failed"
        logger.error(msg)
    
    # Check 2: API Key availability
    if not settings.deepseek_api_key:
        msg = "DEEPSEEK_API_KEY not configured"
        validation_result["warnings"].append(msg)
        validation_result["checks"]["llm"] = "warning"
        logger.warning(msg)
    else:
        validation_result["checks"]["llm"] = "ok"
    
    # Check 3: Trading platform readiness
    if settings.trading_mode == "live":
        validation_result["checks"]["trading_platform"] = "ok"
        logger.info("Trading platform: live mode configured")
    else:
        validation_result["checks"]["trading_platform"] = "dry_run"
        logger.info("Trading platform: dry_run mode")
    
    # Check 4: Risk parameters validity
    if settings.max_single_cny <= 0 or settings.max_daily_cny <= 0:
        msg = "Invalid risk parameters (must be positive)"
        validation_result["errors"].append(msg)
        validation_result["checks"]["risk_params"] = "failed"
        logger.error(msg)
    else:
        validation_result["checks"]["risk_params"] = "ok"
    
    # Check 5: Circuit breaker status
    try:
        if state.get("circuit_breaker"):
            msg = "Circuit breaker is active - cycle may be blocked"
            validation_result["warnings"].append(msg)
            validation_result["checks"]["circuit_breaker"] = "warning"
            logger.warning(msg)
        else:
            validation_result["checks"]["circuit_breaker"] = "ok"
    except Exception as exc:
        logger.warning("Could not check circuit breaker: %s", exc)
    
    # Determine overall status
    validation_result["ok"] = len(validation_result["errors"]) == 0
    
    return validation_result


def should_skip_cycle(settings: Any, db: Any) -> tuple[bool, str]:
    """Determine if cycle should be skipped based on current state.
    
    Args:
        settings: Application settings.
        db: Database instance.
        
    Returns:
        Tuple of (should_skip, reason).
    """
    try:
        state = db.get_risk_state()
        
        # Skip if circuit breaker is active
        if state.get("circuit_breaker"):
            return True, "circuit_breaker_active"
        
        # Skip if daily limit already reached
        daily_spent = float(state.get("spent_cny", 0))
        if daily_spent >= settings.max_daily_cny:
            return True, f"daily_limit_reached_{daily_spent}"
        
        return False, "ok"
    except Exception as exc:
        logger.warning("Error checking skip conditions: %s", exc)
        return False, "validation_error"


class CycleExecutor:
    """Manages cycle execution with timeout and validation."""
    
    def __init__(self, settings: Any, db: Any, max_cycle_duration: float = 120.0):
        self.settings = settings
        self.db = db
        self.max_cycle_duration = max_cycle_duration
    
    def execute(self, run_cycle_func, run_id: str) -> dict[str, Any]:
        """Execute a trading cycle with full protection.
        
        Args:
            run_cycle_func: Function to execute the cycle.
            run_id: Unique cycle run identifier.
            
        Returns:
            Cycle execution result.
        """
        result = {
            "run_id": run_id,
            "status": "pending",
            "validated": False,
            "validation_warnings": [],
        }
        
        try:
            # Step 1: Validate prerequisites
            validation = validate_cycle_prerequisites(self.settings, self.db)
            result["validated"] = validation["ok"]
            result["validation_warnings"] = validation["warnings"]
            
            if not validation["ok"]:
                result["status"] = "validation_failed"
                result["errors"] = validation["errors"]
                logger.error(
                    "Cycle validation failed",
                    extra={"errors": validation["errors"]}
                )
                return result
            
            # Step 2: Check if should skip
            should_skip, reason = should_skip_cycle(self.settings, self.db)
            if should_skip:
                result["status"] = "skipped"
                result["reason"] = reason
                logger.info("Cycle skipped: %s", reason)
                return result
            
            # Step 3: Execute with timeout
            with cycle_timeout(self.max_cycle_duration) as check_timeout:
                start_time = time.time()
                
                # Run the actual cycle
                cycle_result = run_cycle_func(run_id=run_id)
                
                # Check timeout didn't occur
                check_timeout()
                
                elapsed = time.time() - start_time
                cycle_result["cycle_duration_seconds"] = elapsed
                
                logger.info(
                    "Cycle completed successfully",
                    extra={
                        "run_id": run_id,
                        "duration_seconds": elapsed,
                        "status": cycle_result.get("status"),
                    }
                )
                
                return cycle_result
        
        except CycleTimeout as exc:
            result["status"] = "timeout"
            result["error"] = str(exc)
            logger.error(
                "Cycle execution timeout",
                extra={"run_id": run_id, "error": str(exc)}
            )
            return result
        
        except Exception as exc:
            result["status"] = "error"
            result["error"] = str(exc)
            logger.exception(
                "Unexpected error during cycle execution",
                extra={"run_id": run_id}
            )
            return result
