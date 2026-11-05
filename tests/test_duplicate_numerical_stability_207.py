import math
import pytest
from phase_studio import app as a


@pytest.mark.parametrize('sigma',[1e-200,1e200])
def test_duplicate_weights_do_not_overflow_or_underflow(sigma):
    rows=[a.Reflection(1,0,0,10,sigma),a.Reflection(1,0,0,20,2*sigma)]
    result=a.merge_duplicate_reflections(rows,a.REFLECTION_DATA_MODE_INTENSITY)[0]
    assert math.isfinite(result.value)
    assert result.value==pytest.approx(12,rel=1e-14)
    assert result.sigma==pytest.approx(sigma/math.sqrt(1.25),rel=1e-14,abs=0)


def test_duplicate_finite_weighted_mean_cannot_overflow():
    rows=[a.Reflection(1,0,0,1e308,1),a.Reflection(1,0,0,1e308,1)]
    result=a.merge_duplicate_reflections(rows,a.REFLECTION_DATA_MODE_INTENSITY)[0]
    assert math.isfinite(result.value)
    assert result.value==pytest.approx(1e308,rel=1e-14)
