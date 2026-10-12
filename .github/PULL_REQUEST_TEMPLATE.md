## Change

Describe the change and why it is needed, with a link to any related issue.

## Checks

- [ ] Add or update tests for changes to configuration, CLI checks or failure handling.
- [ ] Run the checks below and explain any failures or skipped checks.
- [ ] Update the documentation and changelog where the change affects users.

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile sudo_yubikey.py
bash -n sudo-yubikey.sh
shellcheck sudo-yubikey.sh
```
