# Publish the committed state of this project (branch main) to GitHub
# catawalks/Sindoh under klipper_port/, via the separate clone in
# D:\DP200\backup\sindoh_publish. Commit here first; this only merges what is
# committed. Uncommitted files and the working folder are never touched.
#
#   powershell -File tools\publish_to_sindoh.ps1          merge + push
#   powershell -File tools\publish_to_sindoh.ps1 -NoPush  merge only (look first)
param([switch]$NoPush)
$ErrorActionPreference = 'Stop'
$g = 'C:\Program Files\Git\cmd\git.exe'
$pub = 'D:\DP200\backup\sindoh_publish'

& $g -C $pub pull -q --ff-only origin main          # pick up edits made on GitHub
& $g -C $pub fetch -q port
& $g -C $pub merge -q -s subtree -X subtree=klipper_port -m 'Update klipper_port' port/main
& $g -C $pub log --oneline -3
if (-not $NoPush) { & $g -C $pub push origin main }
