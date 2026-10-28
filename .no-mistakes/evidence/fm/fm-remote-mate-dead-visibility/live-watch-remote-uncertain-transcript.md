# Live watcher transcript: persistent remote secondmate probe failures (lab homes, real bin/fm-watch.sh, FM_SECONDMATE_LIVENESS_UNCERTAIN_TICKS=3)

## Shape 1: unavailable (real ssh -> fm-lab-nohost.invalid, exit 255)
### watcher stdout (wake)
check: secondmate rsm1 liveness remains unavailable after 3 consecutive probes; endpoint was not changed
### triage log
[2026-10-28T15:15:37+0530] secondmate rsm1 liveness: remote host unavailable or endpoint state unknown; route preserved on fm-lab-nohost.invalid
[2026-10-28T15:15:39+0530] secondmate rsm1 liveness: remote host unavailable or endpoint state unknown; route preserved on fm-lab-nohost.invalid
[2026-10-28T15:15:53+0530] secondmate rsm1 liveness: remote host unavailable or endpoint state unknown; route preserved on fm-lab-nohost.invalid
[2026-10-28T15:15:54+0530] secondmate rsm1 liveness: remote host unavailable or endpoint state unknown; route preserved on fm-lab-nohost.invalid
[2026-10-28T15:15:56+0530] secondmate rsm1 liveness: remote host unavailable or endpoint state unknown; route preserved on fm-lab-nohost.invalid
[2026-10-28T15:15:58+0530] secondmate rsm1 liveness: remote host unavailable or endpoint state unknown; route preserved on fm-lab-nohost.invalid
[2026-10-28T15:15:59+0530] secondmate rsm1 liveness: remote host unavailable or endpoint state unknown; route preserved on fm-lab-nohost.invalid
[2026-10-28T15:16:01+0530] secondmate rsm1 liveness: remote host unavailable or endpoint state unknown; route preserved on fm-lab-nohost.invalid
[2026-10-28T15:16:02+0530] secondmate rsm1 liveness: remote host unavailable or endpoint state unknown; route preserved on fm-lab-nohost.invalid
[2026-10-28T15:16:04+0530] secondmate rsm1 liveness: remote host unavailable or endpoint state unknown; route preserved on fm-lab-nohost.invalid
[2026-10-28T15:16:57+0530] secondmate rsm1 liveness: remote endpoint probe unreadable on fm-lab-nohost.invalid
### drained wake row
1793180740	1	check	secondmate-liveness-uncertain-rsm1	check: secondmate rsm1 liveness remains unavailable after 3 consecutive probes; endpoint was not changed
### repeat watcher after ack: stdout
[] (stayed running 12s, killed; 0 new rsm1 rows)
### verdict flip unavailable->unreadable in same episode: stdout
check: rearm-resurface
(rearm-resurface is the pre-existing watcher-downtime wake; no new liveness row queued)
### final episode marker
unreadable	12
### route meta
window=remote:rsm1
kind=secondmate
harness=claude
remote_host=fm-lab-nohost.invalid
remote_backend=herdr
remote_herdr_session=fm-remote
remote_target=fm-remote:w4F:pG
home=/remote/rsm1-home
(unchanged)
ls: /var/folders/81/55x2dv310px5drcswsjgh8qm0000gn/T//fm-lab.pRNhpS/state/.secondmate-relaunch-rsm1: No such file or directory

## Shape 2: unreadable (real fm-on.sh refuses route, exit 1)
### watcher stdout (wake)
check: secondmate rsm1 liveness remains unreadable after 3 consecutive probes; endpoint was not changed
### wake queue
1793180804	1	check	secondmate-liveness-uncertain-rsm1	check: secondmate rsm1 liveness remains unreadable after 3 consecutive probes; endpoint was not changed
### triage log
[2026-10-28T15:16:40+0530] secondmate rsm1 liveness: remote endpoint probe unreadable on fm-lab-host
[2026-10-28T15:16:42+0530] secondmate rsm1 liveness: remote endpoint probe unreadable on fm-lab-host
### markers
unreadable	3 / alerted
(route meta unchanged)
ls: /var/folders/81/55x2dv310px5drcswsjgh8qm0000gn/T//fm-lab.lXTEZM/state/.secondmate-relaunch-rsm1: No such file or directory
