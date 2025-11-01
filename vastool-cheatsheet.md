# vastool Command Cheat‑Sheet (from BashPi)

> Source: [BashPi — *vastool cheat‑sheet*](https://www.bashpi.org/?page_id=803)

This file summarizes the functionality and common options for `vastool`, the command‑line utility shipped with One Identity / Quest Safeguard Authentication Services (SAS, formerly VAS). It focuses on the commands and examples covered by the BashPi page linked above.

## Contents
- [Basics](#basics)
- [Status](#vastool-status)
- [Flush caches](#vastool-flush)
- [Join / Unjoin](#vastool-join--vastool-unjoin)
- [Search (LDAP)](#vastool-search)
- [Attributes](#vastool-attrs)
- [List users/groups](#vastool-list)
- [User tools](#vastool-user)
- [Group tools](#vastool-group)
- [Create / Delete objects](#vastool-create--vastool-delete)
- [Password / Keytabs](#vastool-passwd)
- [Kerberos (kinit, klist, kdestroy, ktutil)](#kerberos-kinit-klist-kdestroy-ktutil)
- [Info / Inspect / Configure / Setattrs](#vastool-info--vastool-inspect--vastool-configure--vastool-setattrs)
- [Daemon wrapper](#vastool-daemon)
- [Licenses](#vastool-license)

---

## Basics
```bash
/opt/quest/bin/vastool [-vsq] [-h [command]] [-u username] [-w password] [-k keytab] command [args]
```
- `-u` user/principal to run as (e.g., `-u host/` on a joined host)  
- `-w` password (otherwise it prompts)  
- `-k` keytab to authenticate  
- `-d`/`-e` debug / error verbosity levels  
Run `vastool` with no args to see the **Available commands** list.

---

## `vastool status`
Quick health snapshot of the QAS/SAS environment.
```bash
vastool status        # basic status
vastool status -v     # verbose
vastool status -c     # CSV
```
Useful to confirm the version, joined domain, SELinux notices, and pass/fail checks.

---

## `vastool flush`
Flush (and optionally reload) various caches to avoid anomalies after config changes.
```bash
vastool flush                 # flush all
vastool flush users           # or specific cache: users, groups, netgroup, auth, srvinfo, ccaches, etc.
vastool flush -r users        # don’t reload after flushing
```
> Hint from BashPi: Equivalent concept to `sss_cache -E` when using SSSD.

---

## `vastool join` / `vastool unjoin`
Join a host to AD (with username/password or keytab); or remove it.
```bash
# Join with admin principal + keytab, set computer name & container
vastool -u adminuser -k admin.user.keytab join -n host01 \
  -c 'OU=Servers,DC=example,DC=com' example.com

# Join with pre-generated **host** keytab (centralized join model)
vastool -u host/ -k host.keytab join -f -n host01.example.com

# Pin site & controllers on an already‑joined host
vastool -u host/ -k host.keytab join -f -n host01.example.com \
  -s READONLY-SITE example.com dc1.example.com dc2.example.com

# Unjoin (leave domain)
vastool -u adminuser -k admin.user.keytab unjoin
```
Notable join options: `--skip-config`, `--no-timesync`, `--autogen-posix-attrs`, `-c` (container DN), `-n` (computer name).

---

## `vastool search`
Run LDAP searches with flexible filters/attributes.
```bash
# All attrs for a user by sAMAccountName
vastool -u host/ search 'samaccountname=johndoe'

# Only membership
vastool -u host/ search 'samaccountname=johndoe' memberof

# Count groups (skip the DN line)
vastool -u host/ search 'samaccountname=johndoe' memberof | grep -iv '^dn:' | wc -l

# Find by UNIX IDs
vastool -u host/ search 'uidNumber=1000'
vastool -u host/ search 'gidNumber=1000'

# Objects a user "owns"
vastool -u host/ search 'samaccountname=johndoe' directReports
vastool -u host/ search 'samaccountname=johndoe' managedObjects

# Users with "password never expires"
vastool -u host/ search -q '(&(objectCategory=person)(useraccountcontrol>=65536)(useraccountcontrol<=131072))' samAccountName

# Group lookup
vastool -u host/ search 'samaccountname=usergroup77' member
```
Timestamps like `msDS-UserPasswordExpiryTimeComputed` or `lockoutTime` can be parsed to human‑readable dates by slicing off the final 7 digits (100‑ns units) and converting from `1601‑01‑01 UTC` with `date`.

---

## `vastool attrs`
List attributes for a **single** object (user/group/computer/DN).
```bash
vastool -u host/ attrs -u johndoe
vastool -u host/ attrs -g 'usergroup77'
vastool -u host/ attrs -d 'CN=host01,OU=Servers,DC=example,DC=com'
# Verify host is a member of a group:
vastool -u host/ attrs -g "Linux Servers" member | grep "member: CN=host01"
```

---

## `vastool list`
Enumerate users, groups, and related cache information.
```bash
vastool list users
vastool list groups
vastool list user johndoe
vastool list group usergroup77

# All (including non‑UNIX‑enabled) — beware size/perf in large domains
vastool -u host/ list -al users
vastool -u host/ list -al groups

# Who can login (or is denied) per local cache
vastool list users-allowed
vastool list users-denied
```
Key flags: `-l` (bypass cache; query LDAP), `-c` (read cache only), `-a` (include non‑UNIX‑enabled), `-u` (unroll group nesting), `-s/-p/-t/-g/-n` (extra fields).

---

## `vastool user`
Check access and reveal what grants/denies it; examine groups.
```bash
vastool user checkaccess johndoe
vastool user getgroups -p johndoe
```
`checkaccess` will name the rule (e.g., “Allow Group …”) that permits login.

---

## `vastool group`
Modify AD group membership from the CLI.
```bash
# Add the local host computer account to a group
vastool -u adminuser -k admin.user.keytab group "Linux Servers" add host/$(hostname)

# Other forms
vastool group <group> add <user...>
vastool group <group> del <user...>
vastool group <group> hasmember <user...>
```

---

## `vastool create` / `vastool delete`
Create users/groups/computers (incl. UNIX‑enable), or delete objects.
```bash
# Create only the computer object (don’t join)
vastool -u adminuser -k admin.user.keytab create -c "OU=Servers,DC=example,DC=com" -o computer host01

# Delete a computer object
vastool -u adminuser -k admin.user.keytab delete computer host01
```
Useful flags on `create`: `-c` container DN, `-i` passwd/group‑style info (for UNIX‑enable), `-e` UNIX‑enable existing user/group, `-t` group type, `-x` don’t force PW change at first login.

---

## `vastool passwd`
Change passwords and (critically) generate keytabs.
```bash
# Reset computer account password AND write a new host keytab (random)
vastool -u adminuser -k admin.user.keytab passwd -rk /root/host01.example.com.keytab host01
```
Other flags: `-o` (print new password), `-p` (send to PDC), `-x` (must change at next login), `-e` (DES keys in keytab).

---

## Kerberos (`kinit`, `klist`, `kdestroy`, `ktutil`)
```bash
# Obtain TGT (password or keytab)
vastool kinit myuser
vastool -k my.keytab kinit myuser

# List tickets
vastool klist
vastool klist -v -c FILE:/tmp/krb5cc_0

# Destroy tickets
vastool kdestroy

# Manage keytabs
vastool ktutil list
vastool ktutil -k /etc/opt/quest/vas/host.keytab list
vastool ktutil -k /root/host01.example.com.keytab alias host01@EXAMPLE.COM host/host01.example.com
```
`ktutil` subcommands: `alias`, `list [--keys|--timestamp]`, `remove -p <principal> [-V <kvno>] [-e <enc>]`

---

## `vastool info` / `vastool inspect` / `vastool configure` / `vastool setattrs`
- `info` — environment details (site, domains, DCs, policies, `toconf` to write configs):
  ```bash
  vastool -u host/ info toconf ./krb5.conf
  ```
- `inspect` — read values from `vas.conf` (e.g., `vasd timesync-interval`, `user-search-path`).
- `configure` — write config (e.g., `configure pam`, `configure nss`, or set `vasd` keys):
  ```bash
  vastool configure vas vasd timesync-interval 0
  vastool configure vas vasd user-search-path "OU=unix,DC=example,DC=com; OU=unix,DC=sub,DC=example,DC=com"
  vastool configure vas vasd group-search-path "OU=unix,DC=example,DC=com; OU=unix,DC=sub,DC=example,DC=com"
  vastool configure vas vas_auth perm-disconnected-users bob johndoe usergroup77
  ```
- `setattrs` — modify LDAP attributes (supports multi‑value with `-m`, remove with `-r`):
  ```bash
  # Add/replace SPNs (include all existing values when updating multi‑value attrs)
  vastool -u adminuser -k admin.user.keytab setattrs -m host/ \
    servicePrincipalName spn1 spn2 ... spnN
  ```

---

## `vastool daemon`
Wrapper around the OS service manager (e.g., `systemctl`).
```bash
vastool daemon restart vasd
vastool daemon restart sshd
```

---

## `vastool license`
Show license totals/details or add a license file.
```bash
vastool license -q       # totals
vastool license -i       # per‑license detail
vastool license add /path/to/license.file
```

---

### Notes
- Many commands accept `-u host/` on a joined host to authenticate as the machine principal with its keytab.
- When editing multi‑value LDAP attributes (like `servicePrincipalName`) you typically provide the **full** desired set on update.
- For deeper coverage not on the BashPi page, consult the official *vastool* man pages in your installed version.
