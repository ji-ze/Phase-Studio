"""Offline bibliographic metadata; original project CFF remains authoritative.

Journal metadata checked against publisher records on 2026-11-09:
https://onlinelibrary.wiley.com/doi/abs/10.1107/S0021889807029238
https://onlinelibrary.wiley.com/doi/abs/10.1107/S0021889812016068
The 2025 conference abstract at https://xray.cz/xray/csca/kol2025/files/600.htm
does not establish a SharpED software journal article. Its provisional software
credit below uses the project's approved development credits, without a year,
version or DOI. No publication is inferred from search absence.
"""
from dataclasses import dataclass
from .legal_content import citation_text, citation_fields


@dataclass(frozen=True)
class Reference:
    key: str
    name: str
    title: str
    authors: str
    citation: str
    status: str
    url: str
    year: str = ''
    journal: str = ''
    volume: str = ''
    pages: str = ''
    doi: str = ''
    version: str = ''

    def bibtex(self):
        fields = dict(title=self.title, author=self.authors, year=self.year,
                      journal=self.journal, volume=self.volume, pages=self.pages,
                      doi=self.doi, url=self.url, version=self.version)
        lines = [f'@{"article" if self.doi else "misc"}{{{self.key},']
        for key, value in fields.items():
            if value:
                safe = value.replace('\\', r'\textbackslash{}').replace('{', r'\{').replace('}', r'\}')
                lines.append(f'  {key} = {{{safe}}},')
        if not self.doi:
            lines.append('  note = {' + self.status + '},')
        return '\n'.join(lines + ['}'])


def references(runtime_version):
    fields = citation_fields()
    text = citation_text(runtime_version)
    title = fields.get('title', 'Phase Studio')
    authors = text.split(', ' + title + ', version ', 1)[0].replace('; ', ' and ')
    return (
        Reference('PhaseStudio', title, title, authors, text,
                  'Software · development version; no publication date or DOI asserted',
                  fields.get('repository-code', ''), version=runtime_version),
        Reference('Superflip2007', 'Superflip',
                  'SUPERFLIP – a computer program for the solution of crystal structures by charge flipping in arbitrary dimensions',
                  'Palatinus, L. and Chapuis, G.',
                  'Palatinus, L. & Chapuis, G. (2007). SUPERFLIP – a computer program for the solution of crystal structures by charge flipping in arbitrary dimensions. Journal of Applied Crystallography, 40, 786–790. https://doi.org/10.1107/S0021889807029238',
                  'Verified journal reference', 'https://doi.org/10.1107/S0021889807029238',
                  year='2007', journal='Journal of Applied Crystallography', volume='40', pages='786--790', doi='10.1107/S0021889807029238'),
        Reference('EDMA2012', 'EDMA',
                  'EDMA: a computer program for topological analysis of discrete electron densities',
                  'Palatinus, L. and Prathapa, S. J. and van Smaalen, S.',
                  'Palatinus, L., Prathapa, S. J. & van Smaalen, S. (2012). EDMA: a computer program for topological analysis of discrete electron densities. Journal of Applied Crystallography, 45, 575–580. https://doi.org/10.1107/S0021889812016068',
                  'Verified journal reference', 'https://doi.org/10.1107/S0021889812016068',
                  year='2012', journal='Journal of Applied Crystallography', volume='45', pages='575--580', doi='10.1107/S0021889812016068'),
        Reference('SharpED', 'SharpED', 'SharpED',
                  'Zelenka, J. and Rohlíček, J. and Kučeráková, M. and Buk, Z.',
                  'Zelenka, J., Rohlíček, J., Kučeráková, M. & Buk, Z. SharpED [scientific software]. https://sharped.fzu.cz/',
                  'Provisional software citation · journal citation not verified', 'https://sharped.fzu.cz/'),
    )
