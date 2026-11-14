from pathlib import Path
import subprocess
from phase_studio.legal_content import source_text,citation_fields,citation_text


def test_authorship_and_citation_are_separate_from_sharped_credits():
    authors=source_text('AUTHORS.md')
    assert 'author and lead developer: **Jiří Zelenka**' in authors
    assert 'mailto:zelenka@fzu.cz' in authors
    assert 'mailto:kucerakova@fzu.cz' in authors
    assert 'mailto:rohlicek@fzu.cz' in authors
    assert 'separate scientific project' in authors
    fields=citation_fields()
    assert fields['license']=='MIT' and fields['cff-version']=='1.2.0'
    assert 'version 9.8.7' in citation_text('9.8.7')
    cff=source_text('CITATION.cff')
    assert cff.count('family-names:')==1 and 'email: zelenka@fzu.cz' in cff
    assert 'Kučeráková' not in cff


def test_authoritative_license_and_existing_notices_are_byte_preserved():
    root=Path(__file__).resolve().parents[1]
    for name in ('LICENSE','THIRD_PARTY_NOTICES.md','phase_studio/assets/fonts/OFL-Science-Gothic.txt'):
        before=subprocess.check_output(['git','show','2eae1ecd0c83dc6e19d9a99b302d3f479282fc70:'+name],cwd=root)
        # Git normalizes checkout line endings; compare original logical bytes.
        assert (root/name).read_bytes().replace(b'\r\n',b'\n')==before.replace(b'\r\n',b'\n')
