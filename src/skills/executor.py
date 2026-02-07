"""Sandboxed skill code executor."""

import sys
import subprocess
import traceback
import logging
from io import StringIO
from dataclasses import dataclass
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from .parser import Skill

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of skill execution."""
    success: bool
    result: Any = None
    error: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    
    def __str__(self) -> str:
        if self.success:
            return str(self.result)
        return f"Error: {self.error}"


class SkillExecutor:
    """Execute skill code in a sandboxed environment."""
    
    # Restricted builtins for sandboxed execution
    SAFE_BUILTINS = {
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "chr": chr,
        "dict": dict,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "format": format,
        "frozenset": frozenset,
        "getattr": getattr,
        "hasattr": hasattr,
        "hash": hash,
        "int": int,
        "isinstance": isinstance,
        "issubclass": issubclass,
        "iter": iter,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "next": next,
        "ord": ord,
        "pow": pow,
        "print": print,
        "range": range,
        "repr": repr,
        "reversed": reversed,
        "round": round,
        "set": set,
        "slice": slice,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "type": type,
        "zip": zip,
        # Allow __import__ for skills that need external packages
        "__import__": __import__,
    }
    
    # Allowed modules that can be imported
    ALLOWED_MODULES = {
        "requests",
        "httpx",
        "json",
        "datetime",
        "time",
        "re",
        "math",
        "random",
        "urllib",
        "base64",
        "hashlib",
        "os.path",  # Only path operations
    }
    
    def __init__(self, timeout: int = 30, auto_install: bool = True):
        """Initialize executor with timeout in seconds."""
        self.timeout = timeout
        self.auto_install = auto_install
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._installed_packages: set[str] = set()
    
    def _install_dependencies(self, dependencies: list[str]) -> tuple[bool, str]:
        """Install missing dependencies via pip."""
        for dep in dependencies:
            if dep in self._installed_packages:
                continue
            
            # Check if already importable
            try:
                __import__(dep)
                self._installed_packages.add(dep)
                continue
            except ImportError:
                pass
            
            # Try to install
            logger.info(f"Installing dependency: {dep}")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", dep, "--quiet"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    return False, f"Failed to install {dep}: {result.stderr}"
                self._installed_packages.add(dep)
            except Exception as e:
                return False, f"Error installing {dep}: {e}"
        
        return True, ""
    
    def _create_sandbox_globals(self) -> dict:
        """Create globals dictionary for execution."""
        # Use real builtins to allow imports to work properly
        return {
            "__builtins__": __builtins__,
            "__name__": "__skill__",
        }
    
    def _execute_code(
        self,
        code: str,
        func_name: str,
        args: dict[str, Any],
    ) -> tuple[Any, str, str]:
        """Execute code and return (result, stdout, stderr)."""
        # Capture stdout/stderr
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = stdout_capture = StringIO()
        sys.stderr = stderr_capture = StringIO()
        
        try:
            # Create sandbox environment
            # Use same dict for globals and locals so module-level variables
            # are accessible inside functions
            sandbox = self._create_sandbox_globals()
            
            # Execute the code to define the function and module-level variables
            exec(code, sandbox, sandbox)
            
            # Get the function
            if func_name not in sandbox:
                raise ValueError(f"Function '{func_name}' not found in skill code")
            
            func = sandbox[func_name]
            
            # Call the function with arguments
            result = func(**args)
            
            return result, stdout_capture.getvalue(), stderr_capture.getvalue()
            
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
    
    def execute(
        self,
        skill: Skill,
        args: Optional[dict[str, Any]] = None,
        func_name: str = "execute",
    ) -> ExecutionResult:
        """Execute a skill with the given arguments."""
        if args is None:
            args = {}
        
        # Auto-install dependencies if enabled
        if self.auto_install and skill.dependencies:
            success, error = self._install_dependencies(skill.dependencies)
            if not success:
                return ExecutionResult(
                    success=False,
                    error=f"Dependency installation failed: {error}",
                )
        
        try:
            # Submit execution to thread pool with timeout
            future = self._executor.submit(
                self._execute_code,
                skill.code,
                func_name,
                args,
            )
            
            try:
                result, stdout, stderr = future.result(timeout=self.timeout)
                return ExecutionResult(
                    success=True,
                    result=result,
                    stdout=stdout,
                    stderr=stderr,
                )
            except FuturesTimeoutError:
                future.cancel()
                return ExecutionResult(
                    success=False,
                    error=f"Execution timed out after {self.timeout} seconds",
                )
                
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                stderr=traceback.format_exc(),
            )
    
    def validate_code(self, code: str) -> tuple[bool, Optional[str]]:
        """Validate that code is syntactically correct and has execute function."""
        try:
            # Check syntax
            compile(code, "<skill>", "exec")
            
            # Check for execute function definition
            if "def execute(" not in code:
                return False, "Code must contain a 'def execute(' function"
            
            return True, None
            
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"
    
    def test_skill(self, skill: Skill) -> ExecutionResult:
        """Test a skill with no arguments to verify it works."""
        return self.execute(skill, args={})
