# Fake vastool test environment

This workspace contains a small fake implementation of `vastool` and a
tiny CSV database so you can exercise tooling that expects the real
`vastool` (One Identity / Quest Safeguard Authentication Services).

Files added
- `vastool` — executable Python script that mimics many common
  `vastool` subcommands and prints deterministic, production-like
  outputs. It reads user data from `fake_users.csv`.
- `fake_users.csv` — CSV file with 10 fake AD-style user records. Each
  row contains typical attributes you would see in AD (dn, cn,
  sAMAccountName, uidNumber, gidNumber, memberOf, mail, sn, givenName,
  telephoneNumber, accountExpires, lockoutTime, userAccountControl).

Supported features
- `search` accepts either simple `key=value` filters or LDAP-style
  filters (examples below). Searches and `attrs` now read from
  `fake_users.csv`.
- LDAP-style filters support a subset of operators: `&` (AND), `|`
  (OR), `!` (NOT), equality (`=`), numeric comparisons (`>=`, `>`, `<=`,
  `<`), presence (`attr=*`), and simple substring patterns with `*`.

Quick examples

Run the fake `vastool` (script is executable):

```bash
# list users
./vastool list users

# simple key=value search
./vastool search samaccountname=johndoe samAccountName memberOf

# LDAP-style equality
./vastool search '(samaccountname=johndoe)' samAccountName memberOf

# LDAP-style AND: users who are in Admins and have userAccountControl >= 512
./vastool search '(&(userAccountControl>=512)(memberOf=Admins))' samAccountName memberOf

# show all attributes for a user
./vastool attrs -u johndoe

# check group membership
./vastool group "Linux Servers" hasmember johndoe

# JSON output
You can ask `vastool` to produce machine-readable JSON by adding the
global `--json` flag anywhere in the command line. Examples:

```bash
# JSON list of users
./vastool --json list users

# JSON search result (array of matching records)
./vastool --json search samaccountname=johndoe samAccountName memberOf

# JSON attributes for a user
./vastool --json attrs -u johndoe
```
```

Notes & extension ideas
- The CSV is the single source of truth — edit `fake_users.csv` to
  change the dataset.
- The LDAP filter parser is intentionally small and supports common
  cases used by tests. If you need more complete LDAP semantics
  (substring anchors, escapes, extensibleMatch), I can extend the
  parser or switch to a third-party LDAP filter library.
- If you prefer machine-readable output (JSON/CSV), I can add an
  option like `--json` to produce structured output.

Contact
If you want the fake outputs to match a particular `vastool` version
exactly, paste an example output and I will tune the script to match it
byte-for-byte.
# work_env
Setting up test env with scripts that give output like vastool, etc

Note on codespaces:  in github web for new repo it asks if you want to create a code space on 1st page.

for existing repos it's :

https://docs.github.com/en/codespaces/developing-in-a-codespace/creating-a-codespace-for-a-repository#creating-a-codespace-for-a-repository

Add new key to get paid for models:  in chat window, drop down the model dropdown and pick 'select premier models' or whatever it says.  It will let you pick the company (anthropic, openai, etc) and a pop up window will ask for the API/secret key from that company. you would generate that key at that company site.  Then just paste the key in the popup window that asks for it and then the new models will be available in the dropdown.