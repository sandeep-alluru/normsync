# GitHub Action

Use normsync directly in your GitHub Actions workflow:

```yaml
- name: normsync
  uses: sandeep-alluru/normsync@v0.1.0
  with:
    # TODO: add action inputs
    fail-on-error: "true"
```

Or use the CLI directly:

```yaml
- name: Install normsync
  run: pip install normsync

- name: Run normsync
  run: normsync --help
```
