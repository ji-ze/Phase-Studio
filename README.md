# Phase Studio

Phase Studio is a Qt application for iterative crystallographic reconstruction:
Superflip map calculation, SharpED server deblurring and EDMA peak extraction.

Run the GUI from the project root:

```bash
python -m phase_studio
```

SharpED inference runs on the remote API server. Fill the API token in the
SharpED tab or set `SHARPED_API_TOKEN` before launching the GUI.

The project keeps generated maps, logs and cycle folders out of version control
via `.gitignore`.
