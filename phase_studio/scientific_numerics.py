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
    return basis,upper

def periodic_distance(parameters, first, second):
    """Closest lattice image by three-dimensional bounded sphere enumeration.

    Rounding fractional components alone is valid only for orthogonal cells.
    A QR triangular basis bounds every branch by an already known distance.
    No finite neighbor shell is assumed sufficient for a skew cell.
    """
    basis,upper=_cell_basis(tuple(map(float,parameters)))
    delta=np.asarray(first,dtype=float)-np.asarray(second,dtype=float)
    if delta.shape!=(3,) or not np.all(np.isfinite(delta)):
        raise ValueError('Finite three-dimensional fractional coordinates are required.')
    delta-=np.rint(delta)
    best=float(np.dot(basis@delta,basis@delta))
    if best==0:return 0.
    residual=np.zeros(3)
    visits=0
    def search(i,partial):
        nonlocal best,visits
        if i<0:
            best=min(best,partial);return
        tail=float(upper[i,i+1:]@residual[i+1:])
        center=float(delta[i]+tail/upper[i,i])
        radius=math.sqrt(max(0.,best-partial))/abs(float(upper[i,i]))
        slack=16*np.finfo(float).eps*max(1.,abs(center),radius)
        lo,hi=math.ceil(center-radius-slack),math.floor(center+radius+slack)
        if hi-lo>100000:
            raise ValueError('Unit-cell geometry exceeds the supported lattice-search conditioning.')
        for shift in sorted(range(lo,hi+1),key=lambda n:abs(n-center)):
            visits+=1
            if visits>100000:
                raise ValueError('Unit-cell geometry exceeds the supported lattice-search conditioning.')
            residual[i]=delta[i]-shift
            value=float(upper[i,i]*residual[i]+tail)
            total=partial+value*value
            if total<=best+32*np.finfo(float).eps*max(best,1.):search(i-1,total)
    search(2,0.)
    return math.sqrt(best)

def reflection_number(value):
    """Preserve ordinary legacy decimals; retain small nonzero measurements."""
    x=float(value)
    if not math.isfinite(x):raise ValueError('Cannot serialize a nonfinite reflection value.')
    fixed=f'{x:.7f}'
    # At least seven significant digits even below the old absolute rounding floor.
    if x and abs(float(fixed)-x)>abs(x)*5e-8:
        return format(x,'.16g')
    return fixed

def validate_fourier_hkls(dimensions,hkls):
    """Reject aliases; signed Nyquist endpoints share a real discrete mode."""
    for hkl in hkls:
        if len(hkl)!=3 or any(not math.isfinite(float(h)) or int(h)!=h or abs(int(h))>n//2 for h,n in zip(hkl,dimensions)):
            raise ValueError(f'Map grid {dimensions} undersamples reflection {hkl}; use a finer grid, not aliased Fourier coefficients.')
