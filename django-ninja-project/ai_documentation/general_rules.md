# General Rules (Enhanced Readability & Additional Security Notes)

## Globs

## Python Conventions

- **Type Hints**  
  Use Python type hints (e.g., `from typing import List, Optional`) for maintainability and IDE support.
- **Strict Type Checking**  
  Enforce checks with `mypy` or similar tools.
- **Custom Exceptions**  
  Handle errors using Django’s or Django Ninja’s built-in exceptions (or custom classes).

## Code Style

- **Functional Emphasis**  
  Favor functional programming for utility logic. Keep functions pure where practical.
- **Small, Focused Functions**  
  Write concise, auditable code; large functions are harder to secure.
- **Meaningful Names**  
  Use descriptive identifiers (e.g., `patient_medical_history`, `validate_medical_data`).

## Git Conventions

- **Conventional Commits**  
  Examples: `feat: add secure patient endpoint`, `fix: patch data leak`.
- **Focused Pull Requests**  
  Detailed documentation and thorough tests. Emphasize security reviews before merging.

## Performance

- **Secure Caching**  
  Cache data with Django’s caching framework, ensuring encryption and access controls.
- **Optimized Queries**  
  Use `select_related` / `prefetch_related`; avoid unnecessary queries to protect performance and data security.
- **Modularize**  
  Split Django apps and Ninja routes sensibly for maintainable, efficient code.

## Additional Security Considerations

- **Dependency Management**  
  Pin dependencies (`pip freeze`) and run scans (e.g., `pip-audit`) to avoid vulnerable packages.
- **Security Scanning**  
  Use tools like Bandit for static analysis to catch common security issues.
- **Multi-Factor Authentication**  
  Enforce MFA for admin or privileged accounts to protect critical data.
