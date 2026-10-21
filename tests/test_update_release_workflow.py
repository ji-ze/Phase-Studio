"""Release authority boundaries without invoking GitHub or private credentials."""
from pathlib import Path
import ast

ROOT=Path(__file__).resolve().parents[1]


def test_release_signing_and_publication_boundaries():
    workflow=(ROOT/'.github/workflows/windows-release.yml').read_text(encoding='utf8')
    build,sign,publish=workflow.split('\n  sign:\n')[0],workflow.split('\n  sign:\n')[1].split('\n  publish:\n')[0],workflow.split('\n  publish:\n')[1]
    assert 'PHASE_STUDIO_UPDATE_SIGNING_KEY' not in build+publish
    assert 'environment: phase-studio-release-signing' in sign
    assert 'secrets.PHASE_STUDIO_UPDATE_SIGNING_KEY' in sign
    assert 'environment: phase-studio-release-publication' in publish
    assert 'if: inputs.publish' in publish
    assert 'default: false' in build
    assert 'contents: write' not in build+sign
    assert 'git merge-base --is-ancestor $commit origin/main' in build
    assert 'verify_update_build.py' in build
    assert 'generate --' not in workflow and '--clobber' not in workflow
    assert publish.index('verify --directory verified-download')<publish.index('--draft=false')
    assert 'git/refs' in publish and '--verify-tag --draft' in publish


def test_public_trust_module_contains_no_private_material():
    source=(ROOT/'phase_studio/update_trust.py').read_text(encoding='utf8')
    ast.parse(source)
    assert 'PRIVATE KEY' not in source and 'SIGNING_KEY' not in source
    # A production key may be provisioned later. No test requires inventing one.
    assert 'TRUSTED_KEYS' in source
