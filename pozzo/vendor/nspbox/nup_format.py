"""Independent streaming implementation of the public NUP v1 draft.

Format reference: a55uka/nup, SPEC.md at 744fb7e. No reference code is bundled.
All public operations use bounded reads, cancellation and exclusive final commits.
"""
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from contextlib import contextmanager
import base64, hashlib, io, json, os, re, shutil, stat, struct, tempfile, unicodedata, uuid
import zstandard as zstd

BLOCK=1024*1024
LARGE_FILE=256*1024*1024
MAX_ZSTD_WINDOW=1024*1024*1024  # The backend enforces this value in BYTES.
NONE=0xffffffff
KINDS=('base','update','addon','addon_update','system')
PRESETS={'Fast':1,'Balanced':3,'Smaller':9}
SUPER=struct.Struct('<4sHHQQ32sQQII16s32s')
TOC=struct.Struct('<4sIQQQQQ')
PKG=struct.Struct('<QIIIIBBHIQI20s')
DIR=struct.Struct('<IIIIQ')
FILE=struct.Struct('<IIQQQ32sBBH12s')

def check(cancel):
    if cancel is not None and cancel.is_set():raise InterruptedError('NUP operation cancelled.')

def align(n):return (n+15)//16*16
def require(condition,message):
    if not condition:raise ValueError(message)

def linked(path):
    st=path.lstat()
    return path.is_symlink() or bool(getattr(st,'st_file_attributes',0)&0x400)

def safe_name(name,windows=False):
    require(isinstance(name,str) and name not in ('','.','..') and not any(c in name for c in '/\\\0'), 'Unsafe filename in archive/source.')
    if windows:
        require(not any(ord(c)<32 or c in '<>:"|?*' for c in name) and name[-1] not in '. ', 'A filename cannot be extracted safely on Windows: '+repr(name))
        require(name.split('.')[0].upper() not in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]},'Reserved Windows filename: '+name)
    return name

def path_parts(path):
    require(not str(path).startswith('/'),'Absolute file paths are not allowed.')
    parts=str(path).split('/')
    for name in parts:safe_name(name)
    return parts

def commit_file(temporary,output):
    check(None)
    if os.name=='nt':temporary.rename(output)
    else:os.link(temporary,output);temporary.unlink()

@dataclass
class Source:
    size:int
    opener:object
    stamp:object=None
    validator:object=None

    @classmethod
    def path(cls,path,st=None):
        path=Path(path);st=path.lstat() if st is None else st
        require(not stat.S_ISLNK(st.st_mode) and not getattr(st,'st_file_attributes',0)&0x400,'Linked input files are not supported.')
        stamp=(st.st_size,st.st_mtime_ns,st.st_ctime_ns,st.st_ino)
        def validate():
            s=path.lstat();require(not stat.S_ISLNK(s.st_mode) and not getattr(s,'st_file_attributes',0)&0x400,'Source became a link.')
            require((s.st_size,s.st_mtime_ns,s.st_ctime_ns)==stamp[:3] and (not stamp[3] or s.st_ino==stamp[3]),'Source changed during packaging: '+path.name)
        return cls(st.st_size,lambda:path.open('rb'),stamp,validate)

    @classmethod
    def data(cls,data):return cls(len(data),lambda:io.BytesIO(data))

    def validate(self):
        if self.validator:self.validator()

    def read_small(self,limit=32*1024*1024):
        require(self.size<=limit,'Metadata is too large.')
        self.validate()
        with self.opener() as f:data=f.read(self.size+1)
        require(len(data)==self.size,'Short metadata read.')
        return data

@dataclass
class Package:
    title_id:int
    version:int
    kind:int
    files:dict=field(default_factory=dict)
    directories:set=field(default_factory=set)
    metadata:list=field(default_factory=list)
    flags:int=0
    label:str=''

def tlv_bytes(items):
    return b''.join(struct.pack('<HHI',kind,0,len(data))+data for kind,data in items)

def parse_tlvs(data):
    items=[];at=0
    while at<len(data):
        require(at+8<=len(data),'Truncated metadata TLV.')
        kind,res,size=struct.unpack_from('<HHI',data,at);at+=8
        require(res==0 and size<=len(data)-at,'Invalid metadata TLV bounds.')
        items.append((kind,data[at:at+size]));at+=size
    return items

def validate_packages(packages):
    require(0<len(packages)<=4096,'NUP needs 1–4096 packages.')
    require(sum(p.kind==0 for p in packages)<=1,'NUP v1 permits only one base package.')
    identities=set();base=next((p for p in packages if p.kind==0),None)
    for p in packages:
        require(0<p.title_id<1<<64 and 0<=p.version<=0xffffffff and 0<=p.kind<5,'Invalid package identity.')
        ident=(p.title_id,p.version,p.kind);require(ident not in identities,'Duplicate package identity.');identities.add(ident)
        require(p.flags in (0,1) and (not p.flags or p.kind==1),'Unknown package flags.')
        require(p.kind!=1 or p.flags==int(base is None),'Invalid standalone-update flag.')
        if base and p.kind==1:require(p.title_id&~0x1fff==base.title_id&~0x1fff,'Update belongs to a different game.')
        if base and p.kind==2:require(p.title_id&~0x1fff==base.title_id&~0x1fff,'DLC belongs to a different game.')

@contextmanager
def dedup_stream(source,prefixes,seen,cancel,on_read):
    """Sample during the normal read; only plausible duplicates need a pre-hash."""
    with source.opener() as stream:
        first=stream.read(min(source.size,64*1024))
        require(len(first)==min(source.size,64*1024),'Short source read.')
        fingerprint=(source.size,hashlib.sha256(first).digest())
        if fingerprint not in prefixes or not source.size:
            prefixes.add(fingerprint);yield stream,first,None,None;return
        h=hashlib.sha256(first);count=len(first);on_read(count)
        while b:=stream.read(BLOCK):
            check(cancel);h.update(b);count+=len(b);require(count<=source.size,'Source grew during duplicate checking.');on_read(count)
        require(count==source.size,'Source shrank during duplicate checking.');source.validate()
        digest=h.digest();extent=seen.get((digest,source.size))
        if extent is not None:yield None,None,digest,extent;return
    with source.opener() as stream:yield stream,b'',digest,None

def write_extent(out,source,stream,first,level,large_raw,cancel,on_read,known_digest=None):
    start=out.tell();codec=not (large_raw and source.size>LARGE_FILE) and source.size>0
    h=hashlib.sha256();count=0;failed=False
    try:compressor=zstd.ZstdCompressor(level=level,write_content_size=True).compressobj(size=source.size) if codec else None
    except zstd.ZstdError:compressor=None;codec=False
    b=first or stream.read(BLOCK)
    while b:
        check(cancel);count+=len(b);require(count<=source.size,'Source grew during packaging.');h.update(b)
        try:
            if not failed:out.write(compressor.compress(b) if compressor else b)
        except zstd.ZstdError:failed=True;compressor=None
        on_read(count);b=stream.read(BLOCK)
        # Early raw fallback avoids compressing the rest of an incompressible file.
        if compressor and out.tell()-start>=source.size:failed=True;compressor=None
    require(count==source.size,'Source shrank during packaging.')
    if compressor:
        try:out.write(compressor.flush())
        except zstd.ZstdError:failed=True
    source.validate();stored=out.tell()-start;digest=h.digest()
    if known_digest is not None:require(known_digest==digest,'Source changed after duplicate checking.')
    if failed or (compressor and stored>=source.size):
        out.seek(start);out.truncate();rh=hashlib.sha256();n=0
        with source.opener() as original:
            while b:=original.read(BLOCK):
                check(cancel);out.write(b);rh.update(b);n+=len(b);on_read(n)
        source.validate();require(n==source.size and rh.digest()==digest,'Source changed during raw fallback.')
        stored=source.size;codec=False
    return stored,digest,int(codec)

def pack(packages,output,level=3,large_raw=True,verify=True,notify=lambda *a:None,cancel=None,source_guard=None):
    """Stream files once; re-read only when compression does not save space."""
    validate_packages(packages);require(level in (1,3,9),'Choose compression level 1, 3 or 9.')
    output=Path(output).absolute();require(output.suffix.lower()=='.nup','Output must end in .nup.')
    require(not output.exists(),'Output already exists; choose a new filename.')
    output.parent.mkdir(parents=True,exist_ok=True)
    dirs=[];files=[];children=[];roots=[];pool=bytearray();names={}
    def intern(name):
        data=name.encode('utf-8')
        if data not in names:names[data]=len(pool);pool.extend(data)
        return names[data],len(data)
    for p in packages:
        tree={}
        for path in sorted(p.directories,key=lambda s:s.encode('utf-8')):
            branch=tree
            for name in path_parts(path):branch=branch.setdefault(name,{})
        for path,source in p.files.items():
            parts=path_parts(path);branch=tree
            for name in parts[:-1]:
                require(not isinstance(branch.get(name),Source),'File/directory collision.')
                branch=branch.setdefault(name,{})
            require(parts[-1] not in branch,'Duplicate file/directory path.')
            branch[parts[-1]]=source
        def visit(branch,name,depth=0):
            check(cancel);require(depth<256,'Directory nesting exceeds 255 levels.')
            index=len(dirs);dirs.append(None);start=len(children)
            entries=sorted(branch.items(),key=lambda kv:kv[0].encode('utf-8'));children.extend([None]*len(entries))
            for j,(n,value) in enumerate(entries):
                if isinstance(value,dict):children[start+j]=('dir',visit(value,n,depth+1))
                else:
                    children[start+j]=('file',len(files));files.append([intern(n),value,0,0,bytes(32),0])
            dirs[index]=(intern(name),start,len(entries));return index
        roots.append(visit(tree,''))
    require(len(dirs)+len(files)<NONE,'Too many NUP nodes.')
    pooloff=TOC.size+len(packages)*PKG.size+len(dirs)*DIR.size+len(files)*FILE.size+len(children)*4
    tocsize=align(pooloff+len(pool));require(tocsize<=256*1024*1024,'NUP file table exceeds 256 MiB.')
    bloboff=align(128+tocsize);total=sum(f[1].size for f in files);done=0;seen={};prefixes=set();duplicate_files=0
    require(total+bloboff<=0xffffffffffffffff,'NUP payload exceeds its 64-bit size limit.')
    require(shutil.disk_usage(output.parent).free>=total+bloboff+32*1024*1024,'Not enough free space for the worst-case NUP size.')
    temp=output.with_name(output.name+'.'+uuid.uuid4().hex[:10]+'.partial')
    try:
        with temp.open('xb+') as out:
            out.write(bytes(bloboff))
            for node in files:
                check(cancel);source=node[1];source.validate()
                def on_read(count):notify('Compressing / storing files',3+76*(done+count)/max(total,1))
                with dedup_stream(source,prefixes,seen,cancel,on_read) as (stream,first,known,extent):
                    if extent is not None:
                        off,size,enc=extent;node[2:]=[off,size,known,enc];duplicate_files+=1
                    else:
                        start=align(out.tell());out.write(bytes(start-out.tell()))
                        stored,digest,codec=write_extent(out,source,stream,first,level,large_raw,cancel,on_read,known)
                        if source.size==0:node[2:]=[0,0,digest,0]
                        else:node[2:]=[start,stored,digest,codec];seen[(digest,source.size)]=(start,stored,codec)
                done+=source.size
            meta=[]
            for p in packages:
                data=tlv_bytes(p.metadata);require(len(data)<=32*1024*1024,'Package metadata exceeds 32 MiB.')
                meta.append((out.tell(),len(data)) if data else (0,0));out.write(data)
            end=out.tell();toc=bytearray(tocsize)
            TOC.pack_into(toc,0,b'TOC\1',len(packages),len(dirs),len(files),pooloff,len(pool),0);at=TOC.size
            for p,root,(mo,ms) in zip(packages,roots,meta):
                exefs=romfs=NONE
                for name,index in ((b'exefs','exefs'),(b'romfs','romfs')):
                    first,count=dirs[root][1:]
                    for typ,node in children[first:first+count]:
                        if typ=='dir' and dirs[node][0]==(names.get(name,-1),len(name)):
                            if index=='exefs':exefs=node
                            else:romfs=node
                PKG.pack_into(toc,at,p.title_id,root,exefs,romfs,p.version,p.kind,p.flags,0,0,mo,ms,bytes(20));at+=PKG.size
            for (no,nl),start,count in dirs:DIR.pack_into(toc,at,no,nl,start,count,0);at+=DIR.size
            for (no,nl),s,off,size,digest,codec in files:FILE.pack_into(toc,at,no,nl,s.size,off,size,digest,codec,0,0,bytes(12));at+=FILE.size
            for typ,node in children:struct.pack_into('<I',toc,at,node+(len(dirs) if typ=='file' else 0));at+=4
            toc[pooloff:pooloff+len(pool)]=pool
            identity=b''.join(struct.pack('<QIB',p.title_id,p.version,p.kind) for p in packages)
            header=SUPER.pack(b'NUP\1',128,1,128,tocsize,hashlib.sha256(toc).digest(),bloboff,end,len(packages),0,hashlib.sha256(identity).digest()[:16],bytes(32))
            out.seek(0);out.write(header);out.write(toc);out.flush();os.fsync(out.fileno())
        if verify:
            with Archive(temp,cancel) as archive:archive.verify(lambda s,v:notify(s,80+v*.19))
        for p in packages:
            for source in p.files.values():source.validate()
        if source_guard:source_guard()
        check(cancel);commit_file(temp,output);notify('NUP ready',100)
        return {'output':str(output),'size':end,'source_size':total,'saved_bytes':total-end,'verified':verify,'packages':len(packages),'duplicate_files_skipped':duplicate_files}
    finally:
        if temp.exists():temp.unlink()

class Slice(io.RawIOBase):
    def __init__(self,path,offset,size):self.f=Path(path).open('rb');self.f.seek(offset);self.left=size
    def readable(self):return True
    def readinto(self,b):
        data=self.f.read(min(len(b),self.left));b[:len(data)]=data;self.left-=len(data);return len(data)
    def read(self,n=-1):
        data=self.f.read(self.left if n<0 else min(n,self.left));self.left-=len(data);return data
    def close(self):self.f.close();super().close()

class Archive:
    def __init__(self,path,cancel=None):
        self.path=Path(path);self.cancel=cancel;self.f=self.path.open('rb');self.packages=[];self.files=[];self.dirs=[];self.trees=[]
        self.stamp=(self.path.stat().st_size,self.path.stat().st_mtime_ns)
        try:self._parse()
        except BaseException:self.f.close();raise
    def __enter__(self):return self
    def __exit__(self,*a):self.f.close()
    def read_at(self,off,size):
        require(0<=off<=self.stamp[0] and 0<=size<=self.stamp[0]-off,'Archive offset is out of bounds.')
        self.f.seek(off);data=self.f.read(size);require(len(data)==size,'Truncated archive.');return data
    def unchanged(self):
        s=self.path.stat();require((s.st_size,s.st_mtime_ns)==self.stamp,'NUP changed while reading.')
    def _parse(self):
        check(self.cancel);header=self.read_at(0,128)
        magic,hs,hv,to,ts,th,bo,fs,pc,flags,identity,res=SUPER.unpack(header)
        require(magic==b'NUP\1' and hs>=128 and hv>=1 and to==hs,'Not a supported NUP v1 archive.')
        require(not flags and not any(res) and fs==self.stamp[0] and bo%16==0 and fs>=bo>=to+ts and 0<pc<=4096,'Invalid NUP superblock.')
        require(TOC.size<=ts<=256*1024*1024,'Invalid or excessive NUP table size.')
        toc=self.read_at(to,ts);require(hashlib.sha256(toc).digest()==th,'NUP table SHA-256 mismatch.')
        tm,np,nd,nf,po,ps,tr=TOC.unpack_from(toc)
        require(tm==b'TOC\1' and np==pc and not tr,'Invalid NUP table header.')
        arrays=TOC.size+pc*PKG.size+nd*DIR.size+nf*FILE.size
        require(arrays<=po<=ts and ps<=ts-po and (po-arrays)%4==0,'NUP table arrays exceed their region.')
        pool=toc[po:po+ps];slots=(po-arrays)//4
        def name(off,size,root=False):
            require(off<=ps and size<=ps-off,'Invalid NUP name range.')
            s=pool[off:off+size].decode('utf-8')
            if s or not root:safe_name(s)
            return s
        at=TOC.size;regions=[];records=[]
        for i in range(pc):
            tid,root,ex,rom,ver,kind,pflags,r,r2,mo,ms,r3=PKG.unpack_from(toc,at);at+=PKG.size
            require(root<nd and (ex==NONE or ex<nd) and (rom==NONE or rom<nd) and not r and not r2 and not any(r3),'Invalid NUP package record.')
            require((mo==0)==(ms==0),'Invalid metadata extent.')
            require(ms<=32*1024*1024,'Package metadata exceeds 32 MiB.')
            if ms:require(bo<=mo and ms<=fs-mo,'Invalid package metadata bounds.');regions.append((mo,mo+ms,('meta',i)))
            p=Package(tid,ver,kind,metadata=parse_tlvs(self.read_at(mo,ms)) if ms else [],flags=pflags)
            self.packages.append(p);records.append((root,ex,rom))
        validate_packages(self.packages)
        ident=hashlib.sha256(b''.join(struct.pack('<QIB',p.title_id,p.version,p.kind) for p in self.packages)).digest()[:16]
        require(ident==identity,'NUP identity UUID mismatch.')
        roots={r[0] for r in records};require(len(roots)==pc,'Packages share a root directory.')
        for i in range(nd):
            no,nl,first,count,r=DIR.unpack_from(toc,at);at+=DIR.size
            require(not r and first<=slots and count<=slots-first,'Invalid directory child range.')
            self.dirs.append((name(no,nl,i in roots),first,count))
        extent_ids={}
        for i in range(nf):
            no,nl,size,off,stored,digest,codec,cf,r,r3=FILE.unpack_from(toc,at);at+=FILE.size
            require(codec in (0,1) and not cf and not r and not any(r3),'Unknown codec or file flags.')
            if size==0:require(off==stored==codec==0,'Invalid empty-file extent.')
            else:
                require(bo<=off and off%16==0 and 0<stored<=fs-off,'File extent out of bounds.')
                require(codec!=0 or stored==size,'Raw file size mismatch.')
                key=(off,off+stored);properties=(size,digest,codec)
                require(key not in extent_ids or extent_ids[key]==properties,'Conflicting shared extent.')
                if key not in extent_ids:regions.append((*key,('file',i)));extent_ids[key]=properties
                if codec==1:
                    head=self.read_at(off,min(stored,18));params=zstd.get_frame_parameters(head)
                    require(params.content_size==size and params.dict_id==0,'Zstandard frame size/dictionary is unsupported.')
                    require(params.window_size<=MAX_ZSTD_WINDOW,'Zstandard frame requires a decoder window larger than 1 GiB.')
                    cursor=off+zstd.frame_header_size(head)
                    while True:
                        check(self.cancel);require(cursor+3<=off+stored,'Truncated Zstandard block header.')
                        block=int.from_bytes(self.read_at(cursor,3),'little');cursor+=3
                        last=block&1;kind=(block>>1)&3;blocksize=block>>3
                        require(kind!=3 and blocksize<=128*1024,'Invalid Zstandard block.')
                        cursor+=1 if kind==1 else blocksize
                        require(cursor<=off+stored,'Truncated Zstandard block payload.')
                        if last:break
                    if params.has_checksum:cursor+=4
                    require(cursor==off+stored,'NUP extent must contain exactly one Zstandard frame.')
            self.files.append((name(no,nl),size,off,stored,digest,codec))
        regions.sort()
        for left,right in zip(regions,regions[1:]):require(left[1]<=right[0],'Overlapping NUP extents/metadata.')
        children=[struct.unpack_from('<I',toc,arrays+i*4)[0] for i in range(slots)]
        used=set();used_slots=set()
        for p,(root,ex,rom) in zip(self.packages,records):
            paths={};directories=set();directory_paths={}
            def walk(node,prefix,depth=0):
                check(self.cancel);require(node not in used and depth<256,'Cyclic, shared or overly deep directory tree.');used.add(node)
                directory_paths[node]=prefix
                if prefix:directories.add(prefix)
                _,first,count=self.dirs[node];previous=None
                for slot in range(first,first+count):
                    require(slot not in used_slots,'Overlapping child slot ranges.');used_slots.add(slot)
                    child=children[slot];require(child<nd+nf,'Invalid child node ID.')
                    label=self.dirs[child][0] if child<nd else self.files[child-nd][0];raw=label.encode()
                    safe_name(label);require(previous is None or previous<raw,'Child names are duplicate or unsorted.');previous=raw
                    path=prefix+'/'+label if prefix else label
                    if child<nd:walk(child,path,depth+1)
                    else:
                        require(child not in used,'Shared file node.');used.add(child);paths[path]=child-nd
            walk(root,'')
            for index,label in ((ex,'exefs'),(rom,'romfs')):
                if index!=NONE:require(directory_paths.get(index)==label,'Package content directory does not match its tree.')
            p.directories=directories
            p.files={path:Source(self.files[index][1],lambda i=index:self.open_file(i),validator=self.unchanged) for path,index in paths.items()}
            self.trees.append(paths)
        require(len(used)==nd+nf and len(used_slots)==slots,'Unreferenced NUP nodes or child slots.')
        self.stats={'packages':pc,'files':nf,'uncompressed':sum(f[1] for f in self.files),'stored':sum(k[1]-k[0] for k in extent_ids),'archive_size':fs,
                    'compressed_files':sum(f[5]==1 for f in self.files),'raw_files':sum(f[5]==0 for f in self.files),'unique_extents':len(extent_ids)}
    @contextmanager
    def open_file(self,index):
        _,size,off,stored,digest,codec=self.files[index]
        raw=Slice(self.path,off,stored)
        try:
            if codec:
                with zstd.ZstdDecompressor(max_window_size=MAX_ZSTD_WINDOW).stream_reader(raw,read_across_frames=False,closefd=False) as reader:yield reader
            else:yield raw
        finally:raw.close()
    def file_chunks(self,index):
        _,size,off,stored,digest,codec=self.files[index];h=hashlib.sha256();count=0
        with self.open_file(index) as source:
            while b:=source.read(min(BLOCK,size-count+1)):
                check(self.cancel);count+=len(b);require(count<=size,'Decompressed file exceeds its declared size.');h.update(b);yield b
        require(count==size and h.digest()==digest,'File SHA-256 mismatch: '+self.files[index][0])
    def verify(self,notify=lambda *a:None):
        total=self.stats['uncompressed'];done=0;verified_extents=set()
        for i,file in enumerate(self.files):
            check(self.cancel);key=file[1:]
            if key in verified_extents:done+=file[1]
            else:
                for b in self.file_chunks(i):done+=len(b);notify('Verifying NUP files',100*done/max(total,1))
                verified_extents.add(key)
            notify('Verifying NUP files',100*done/max(total,1))
        self.unchanged();return dict(self.stats,verified=True)
    def inspect(self):
        return dict(self.stats,packages_info=[{'index':i,'kind':KINDS[p.kind],'title_id':f'{p.title_id:016X}','version':p.version,'flags':p.flags,
          'files':len(p.files),'metadata_types':[f'{t:04X}' for t,d in p.metadata],
          'title':next((d.decode('utf-8','replace') for t,d in p.metadata if t==5),'')} for i,p in enumerate(self.packages)])

def package_path(p):
    if p.kind==0:return 'base'
    if p.kind==1:return f'updates/{p.version}'
    if p.kind==2:return f'dlc/{p.title_id:016X}/{p.version}'
    return f'{KINDS[p.kind]}/{p.title_id:016X}/{p.version}'

def extract(path,output,selection=None,notify=lambda *a:None,cancel=None):
    output=Path(output).absolute();require(not output.exists(),'Extract into a new folder; existing files are never overwritten.')
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.nup-extract-',dir=output.parent))
    try:
        with Archive(path,cancel) as archive:
            selected=list(range(len(archive.packages))) if selection is None else list(selection)
            require(selected and len(set(selected))==len(selected) and all(0<=i<len(archive.packages) for i in selected),'Choose a valid package selection.')
            total=sum(archive.files[i][1] for k in selected for i in archive.trees[k].values());done=0;manifest=[];destinations=set()
            require(shutil.disk_usage(stage).free>total+32*1024*1024,'Not enough extraction disk space.')
            for k in selected:
                p=archive.packages[k];relative=package_path(p);require(relative not in destinations,'Duplicate extraction package path.');destinations.add(relative)
                base=stage/relative;base.mkdir(parents=True)
                collision=set()
                for item in sorted(p.directories|set(p.files)):
                    parts=path_parts(item)
                    for part in parts:safe_name(part,windows=os.name=='nt')
                    key=item.casefold() if os.name=='nt' else item
                    require(key not in collision,'Case-colliding names cannot be extracted on this filesystem.');collision.add(key)
                for directory in sorted(p.directories):check(cancel);(base/directory).mkdir(parents=True,exist_ok=True)
                for item,index in archive.trees[k].items():
                    target=base/item;target.parent.mkdir(parents=True,exist_ok=True)
                    with target.open('xb') as f:
                        for b in archive.file_chunks(index):f.write(b);done+=len(b);notify('Extracting verified files',99*done/max(total,1))
                manifest.append({'path':relative,'title_id':f'{p.title_id:016X}','version':p.version,'kind':p.kind,'flags':p.flags,
                                 'metadata':[[t,base64.b64encode(d).decode('ascii')] for t,d in p.metadata]})
            archive.unchanged()
            (stage/'nup-manifest.json').write_text(json.dumps({'format':'NSP Box NUP extraction v1','packages':manifest},indent=2),encoding='utf-8')
        check(cancel);stage.rename(output);notify('Extraction complete',100)
        return {'output':str(output),'size':total,'verified':True,'packages':len(selected)}
    finally:
        if stage.exists():
            require(stage.resolve().is_relative_to(output.parent.resolve()) and not linked(stage),'Temporary extraction folder changed unexpectedly.')
            shutil.rmtree(stage)
