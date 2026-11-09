"""Presentation targets attached at validation sites, never inferred from prose."""


class ValidationIssue(str):
    """A string-compatible issue for existing callers and structured recovery UI."""
    def __new__(cls, message, code, setting='', page='Input', advanced=False):
        issue = super().__new__(cls, message)
        issue.code = code
        issue.setting = setting
        issue.page = page
        issue.advanced = advanced
        return issue

    def __reduce__(self):
        return (type(self), (str(self), self.code, self.setting, self.page, self.advanced))


RECOVERY_LABELS = {
    'significance_fwhm': 'Review significance threshold',
    'powder_wavelength': 'Set measured wavelength',
    'inflip_missing': 'Select .inflip…',
    'hkl_missing': 'Select HKL…',
    'reference_missing': 'Select reference…',
    'model_missing': 'Select model…',
    'superflip_missing': 'Set up Superflip',
    'edma_missing': 'Set up EDMA',
    'work_directory': 'Choose working folder…',
}
