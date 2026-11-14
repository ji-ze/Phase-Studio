"""Numerical guards and exact periodic geometry for scientific interchange."""
from functools import lru_cache
import math
import numpy as np
import gemmi

@lru_cache(maxsize=128)
def _cell_basis(parameters):
    if len(parameters)!=6 or not all(math.isfinite(v) for v in parameters):
        raise ValueError('Finite unit-cell parameters are required.')
    if min(parameters[:3])<=0 or any(not 0<v<180 for v in parameters[3:]):
        raise ValueError('Invalid unit-cell lengths or angles.')
    ca,cb,cg=(math.cos(math.radians(v)) for v in parameters[3:])
    determinant=1-ca*ca-cb*cb-cg*cg+2*ca*cb*cg
    if determinant<=1e-12:
        raise ValueError('Unit-cell geometry is singular or numerically unsupported.')
    basis=np.asarray(gemmi.UnitCell(*parameters).orth.mat,dtype=float)
    _,upper=np.linalg.qr(basis)
    return tuple(tuple(float(v) for v in row) for row in upper)

def periodic_distance(parameters, first, second):
    """Closest lattice image by three-dimensional bounded sphere enumeration.

    Rounding fractional components alone is valid only for orthogonal cells.
    A QR triangular basis bounds every branch by an already known distance.
    No finite neighbor shell is assumed sufficient for a skew cell.
    """
    upper=_cell_basis(tuple(map(float,parameters)))
    if len(first)!=3 or len(second)!=3:
        raise ValueError('Finite three-dimensional fractional coordinates are required.')
    delta=[float(first[i])-float(second[i]) for i in range(3)]
    if not all(math.isfinite(v) for v in delta):
        raise ValueError('Finite three-dimensional fractional coordinates are required.')
    delta=[v-round(v) for v in delta]
    best=sum(sum(upper[i][j]*delta[j] for j in range(i,3))**2 for i in range(3))
    # Orthogonal cells have separable nearest images; no lattice enumeration
    # is needed. This matters for the quadratic atom-deduplication callers.
    if all(float(angle)==90. for angle in parameters[3:]):
        return math.sqrt(best)
    if best==0:return 0.
    residual=[0.,0.,0.]
    visits=0
    def search(i,partial):
        nonlocal best,visits
        if i<0:
            best=min(best,partial);return
        tail=sum(upper[i][j]*residual[j] for j in range(i+1,3))
        center=delta[i]+tail/upper[i][i]
        radius=math.sqrt(max(0.,best-partial))/abs(upper[i][i])
        slack=16*2.220446049250313e-16*max(1.,abs(center),radius)
        lo,hi=math.ceil(center-radius-slack),math.floor(center+radius+slack)
        if hi-lo>100000:
            raise ValueError('Unit-cell geometry exceeds the supported lattice-search conditioning.')
        for shift in sorted(range(lo,hi+1),key=lambda n:abs(n-center)):
            visits+=1
            if visits>100000:
                raise ValueError('Unit-cell geometry exceeds the supported lattice-search conditioning.')
            residual[i]=delta[i]-shift
            value=upper[i][i]*residual[i]+tail
            total=partial+value*value
            if total<=best+32*2.220446049250313e-16*max(best,1.):search(i-1,total)
    search(2,0.)
    return math.sqrt(best)

def reflection_number(value):
    """Preserve ordinary legacy decimals; retain small nonzero measurements."""
    x=float(value)
    if not math.isfinite(x):raise ValueError('Cannot serialize a nonfinite reflection value.')
    fixed=f'{x:.7f}'
    # At least seven significant digits even below the old absolute rounding floor.
    if x and abs(float(fixed)-x)>abs(x)*5e-8:
        # The installed native Superflip reflection parser rejects exponent
        # notation (both e and E), even though Python accepts it. Expand the
        # significant digits without rounding small measurements to zero.
        from decimal import Decimal
        return format(Decimal(format(x,'.16g')),'f')
    return fixed

def validate_fourier_hkls(dimensions,hkls):
    """Reject aliases; signed Nyquist endpoints share a real discrete mode."""
    for hkl in hkls:
        if len(hkl)!=3 or any(not math.isfinite(float(h)) or int(h)!=h or abs(int(h))>n//2 for h,n in zip(hkl,dimensions)):
            raise ValueError(f'Map grid {dimensions} undersamples reflection {hkl}; use a finer grid, not aliased Fourier coefficients.')
