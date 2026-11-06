"""Verify SignPath changed only PE Authenticode fields/certificate appendices.

Never treat a signing service as permission to replace source-built payloads.
"""
import argparse
import struct
from pathlib import Path
import zipfile


def pe_offsets(raw):
    if len(raw)<64 or raw[:2]!=b'MZ':raise ValueError('Invalid DOS image.')
    offset=struct.unpack_from('<I',raw,60)[0]
    if raw[offset:offset+4]!=b'PE\0\0':raise ValueError('Invalid PE signature.')
    optional=offset+24
    size=struct.unpack_from('<H',raw,offset+20)[0]
    magic=struct.unpack_from('<H',raw,optional)[0]
    directory=optional+{0x10b:96,0x20b:112}.get(magic,0)+4*8
    if magic not in (0x10b,0x20b) or directory+8>optional+size or optional+size>len(raw):raise ValueError('Invalid optional header.')
    return optional+64,directory


def assert_signing_only(unsigned,signed):
    checksum,security=pe_offsets(unsigned)
    if pe_offsets(signed)!=(checksum,security):raise ValueError('Signing changed the PE layout.')
    old_offset,old_size=struct.unpack_from('<II',unsigned,security)
    if old_offset or old_size:raise ValueError('The source artifact is already signed; refuse ambiguous resigning.')
    cert_offset,cert_size=struct.unpack_from('<II',signed,security)
    if cert_size<8 or cert_offset%8 or cert_offset<len(unsigned) or cert_offset+cert_size!=len(signed):
        raise ValueError('Invalid appended Authenticode certificate bounds.')
    if cert_offset-len(unsigned)>7 or any(signed[len(unsigned):cert_offset]):raise ValueError('Unexpected bytes before the certificate.')
    left=bytearray(unsigned);right=bytearray(signed[:len(unsigned)])
    for position,length in ((checksum,4),(security,8)):
        left[position:position+length]=b'\0'*length;right[position:position+length]=b'\0'*length
    if left!=right:raise ValueError('Signing changed application/runtime payload bytes.')


def compare_packages(unsigned,signed,version):
    unsigned,signed=Path(unsigned),Path(signed)
    exe=f'PhaseStudio-{version}-x64.exe';archive=f'PhaseStudio-Jana2020-{version}.zip'
    assert_signing_only((unsigned/exe).read_bytes(),(signed/exe).read_bytes())
    with zipfile.ZipFile(unsigned/archive) as before,zipfile.ZipFile(signed/archive) as after:
        first=before.namelist();second=after.namelist()
        if len(first)!=len(set(first)) or len(second)!=len(set(second)) or set(first)!=set(second):raise ValueError('Signing changed the Jana ZIP inventory.')
        if before.testzip() is not None or after.testzip() is not None:raise ValueError('Corrupt Jana ZIP.')
        main=f'PhaseStudio-Jana2020-{version}/Phase_studio.exe'
        if main not in first:raise ValueError('Missing Jana application.')
        for name in first:
            a,b=before.read(name),after.read(name)
            if name==main:assert_signing_only(a,b)
            elif a!=b:raise ValueError('Signing changed an unselected runtime or third-party file: '+name)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unsigned',type=Path,required=True);parser.add_argument('--signed',type=Path,required=True)
    parser.add_argument('--version')
    args=parser.parse_args()
    if args.version:compare_packages(args.unsigned,args.signed,args.version)
    else:assert_signing_only(args.unsigned.read_bytes(),args.signed.read_bytes())
    print('PASS: payload bytes unchanged by Authenticode signing.')


if __name__=='__main__':main()
