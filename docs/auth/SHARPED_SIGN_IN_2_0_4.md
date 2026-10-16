# Connect Phase Studio to SharpED

Select your workflow and click **Sign in with Jana2020** in the connection dialog.
Use your existing Jana2020 account in the default browser. Phase Studio never
asks for your Jana password. No separate account or manual key is required.

The browser shows **Sign-in completed** after authorization. Phase Studio
continues the original action automatically; no second Connect click is needed.
While waiting, **Open browser again** reopens the same sign-in attempt.
**Cancel sign-in** closes the connection dialog and returns to your previous
configuration. Back is hidden during browser authorization. Escape also safely
cancels the connection dialog.
Scientific workflow settings are preserved.

Access remains in application memory for about one hour. If renewal is needed,
complete another browser sign-in. Jana may reuse your browser session where its
policy allows. Renewal preserves the identity of existing inference jobs and
does not submit a replacement job. Explicit account management remains available;
a normal request with valid session authorization does not need another prompt.

For the older method, expand **Use an access key instead**, paste your manually
generated **SharpED access key**, and click **Connect using access key**.
**Remember access on this device**, behind Saving options/Manage saved access,
is enabled by default on Windows and uses Windows Credential Manager. Manual
keys are restored across application/Jana restarts and EXE updates under the
same Windows user and API origin. Unchecking Remember uses the entered key
only for this session and preserves any previously saved key. Only
**Remove saved access** deletes it. Changed saved keys require explicit review
before connecting. Show/Hide,
replacement and removal remain in that expanded section. An active application
connection can be cleared using **Sign out** there; the browser session is unchanged.

**Get an access key** opens https://sharped.fzu.cz/sharp-ed.
Expand **Show access-key instructions** for the verified steps: sign in with your
Jana2020 account if prompted, expand **API tokens for desktop application** using
**Show**, enter **New token name**, click **Create token**, and copy the key.

Successful sign-in establishes authorization. SharpED processing permissions
are enforced by the service when processing starts; sign-in or public model-list
loading alone does not independently verify them. Superflip-only calculations
do not require SharpED sign-in.
