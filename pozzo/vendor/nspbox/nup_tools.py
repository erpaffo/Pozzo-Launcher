"""NUP discovery and conversions, without keys or changes to the NSP builder."""
from pathlib import Path
from contextlib import contextmanager
from dataclasses import dataclass, replace
import base64, hashlib, io, json, mmap, os, re, shutil, struct, tempfile, uuid, stat
from . import engine, container_format as fmt, verify_format as vf
from .nup_format import (Package, Source, Archive, PRESETS, KINDS, check, require,
                        linked, path_parts, safe_name, pack, extract, package_path, commit_file)

REFERENCE_COMMIT='744fb7e30ce3ace787f1839ee3e7f8a010e36c04'

def npdm_id(data):
    require(len(data)>=0x80 and data[:4]==b'META','Invalid NPDM header.')
    off,size=struct.unpack_from('<II',data,0x70)
    require(off>=0x80 and size>=0x20 and off+size<=len(data) and data[off:off+4]==b'ACI0','Invalid NPDM application metadata.')
    return struct.unpack_from('<Q',data,off+0x10)[0]

def tree_sources(root,cancel=None,directory_stamps=None,notify=lambda *a:None):
    root=Path(root);require(root.is_dir() and not linked(root),'Choose an unlinked source folder.')
    files={};directories=set()
    def visit(folder,depth):
        check(cancel);require(depth<256,'Source tree is too deep.')
        if directory_stamps is not None:
            s=folder.stat();directory_stamps[folder]=(s.st_mtime_ns,s.st_ino)
        with os.scandir(folder) as scan:entries=sorted(scan,key=lambda e:e.name.encode('utf-8'))
        for entry in entries:
            check(cancel);safe_name(entry.name)
            if entry.name=='.listing':continue
            st=entry.stat(follow_symlinks=False);p=Path(entry.path)
            require(not stat.S_ISLNK(st.st_mode) and not getattr(st,'st_file_attributes',0)&0x400,'Linked files/folders are not supported: '+p.name)
            name=p.relative_to(root).as_posix()
            if entry.is_dir(follow_symlinks=False):directories.add(name);visit(p,depth+1)
            elif entry.is_file(follow_symlinks=False):
                files[name]=Source.path(p,st)
                if len(files)%1024==0:notify(f'Indexing source files · {len(files):,}',1)
            else:raise ValueError('Special files are not supported: '+p.name)
    visit(root,0);return files,directories

def metadata_for(files,title=''):
    items=[];npdm=files.get('exefs/main.npdm')
    if npdm:items.append((1,npdm.read_small()))
    main=files.get('exefs/main')
    if main:
        with main.opener() as f:head=f.read(0x60)
        if len(head)==0x60 and (head[:4]==b'NSO0' or head[0x10:0x14]==b'NRO0'):items.append((7,head[0x40:0x60]))
    nacp=next((files[p] for p in ('data/control/control.nacp','control/control.nacp','control.nacp') if p in files),None)
    if nacp:
        data=nacp.read_small();items.append((2,data))
        if len(data)==0x4000:
            if not data[0x3215]:
                name=data[:0x200].split(b'\0')[0].decode('utf-8','replace')
                publisher=data[0x200:0x300].split(b'\0')[0].decode('utf-8','replace')
                if name:title=name
                if publisher:items.append((6,publisher.encode()))
            display=data[0x3060:0x3070].split(b'\0')[0]
            if display:items.append((4,display))
    icons=sorted(p for p in files if p.rsplit('/',1)[-1].startswith('icon_') or p.rsplit('/',1)[-1].lower() in ('icon.jpg','icon.png'))
    icon=next((p for p in icons if 'AmericanEnglish' in p),icons[0] if icons else None)
    if icon:items.append((3,files[icon].read_small()))
    if title:items.append((5,title.encode('utf-8')))
    return items

def discover(folder,cancel=None,directory_stamps=None,notify=lambda *a:None):
    """Conventional bundles, or the lossless manifest emitted by our extractor."""
    folder=Path(folder).absolute()
    require(folder.is_dir() and not linked(folder),'Choose an existing, unlinked folder.')
    if folder.name.lower() in ('exefs','romfs'):folder=folder.parent
    manifest=folder/'nup-manifest.json'
    packages=[]
    if manifest.is_file():
        require(manifest.stat().st_size<=64*1024*1024,'Extraction manifest is too large.')
        obj=json.loads(manifest.read_text(encoding='utf-8'))
        require(obj.get('format')=='NSP Box NUP extraction v1','Unknown extraction manifest.')
        for rec in obj['packages']:
            parts=path_parts(rec['path']);root=folder.joinpath(*parts)
            for parent in [root,*root.parents]:
                if parent==folder.parent:break
                require(not linked(parent),'Linked manifest source folder.')
            files,dirs=tree_sources(root,cancel,directory_stamps,notify)
            items=[(int(t),base64.b64decode(d,validate=True)) for t,d in rec['metadata']]
            packages.append(Package(int(rec['title_id'],16),int(rec['version']),int(rec['kind']),files,dirs,items,int(rec['flags']),rec['path']))
        has_base=any(p.kind==0 for p in packages)
        for p in packages:
            if p.kind==1:p.flags=int(not has_base)
        return packages
    def content(path):
        if directory_stamps is not None and path.is_dir():
            s=path.stat();directory_stamps[path]=(s.st_mtime_ns,s.st_ino)
        return (path/'exefs').is_dir() or (path/'romfs').is_dir()
    def add(root,kind,version=0,tid=None):
        files,dirs=tree_sources(root,cancel,directory_stamps,notify)
        require(files,'Empty content package: '+root.name)
        if 'exefs/main.npdm' in files:tid=npdm_id(files['exefs/main.npdm'].read_small())
        if tid is None:
            for parent in [root,*root.parents]:
                match=re.search(r'(?<![0-9A-Fa-f])([0-9A-Fa-f]{16})(?![0-9A-Fa-f])',parent.name)
                if match:tid=int(match.group(1),16);break
                if parent==folder:break
        require(tid is not None,'No original title ID found in NPDM/folder: '+root.name)
        p=Package(tid,version,kind,files,dirs,metadata_for(files,engine.clean_title(folder.name)),label=str(root.relative_to(folder)) or '.')
        packages.append(p)
    bundle=(any((folder/n).is_dir() for n in ('base','updates','dlc')) or folder.name.lower() in ('updates','dlc')) and not content(folder)
    if bundle:
        base=folder/'base'
        if content(base):add(base,0)
        updates=folder if folder.name.lower()=='updates' else folder/'updates'
        if updates.is_dir():
            require(not linked(updates),'Linked updates folder.')
            for root in sorted(updates.iterdir(),key=lambda p:(int(p.name) if p.name.isascii() and p.name.isdecimal() else -1,p.name)):
                if root.is_dir() and root.name.isascii() and root.name.isdecimal() and content(root):add(root,1,int(root.name))
        dlcroot=folder if folder.name.lower()=='dlc' else folder/'dlc'
        if dlcroot.is_dir():
            require(not linked(dlcroot),'Linked DLC folder.')
            for title in sorted(dlcroot.iterdir()):
                if not title.is_dir():continue
                require(not linked(title),'Linked DLC folder.')
                match=re.search(r'(?<![0-9A-Fa-f])([0-9A-Fa-f]{16})(?![0-9A-Fa-f])',title.name)
                require(match,'DLC folder needs its original 16-digit title ID.')
                tid=int(match.group(1),16)
                if content(title):add(title,2,0,tid)
                else:
                    for root in sorted(title.iterdir()):
                        if root.is_dir() and content(root):add(root,2,int(root.name) if root.name.isdecimal() else 0,tid)
    elif content(folder):
        is_dlc=not (folder/'exefs/main.npdm').is_file()
        version=int(folder.name) if folder.name.isascii() and folder.name.isdecimal() and len(folder.name)<=10 else 0
        is_update=folder.parent.name.lower()=='updates'
        add(folder,2 if is_dlc else (1 if is_update else 0),version)
    else:raise ValueError('No extracted exefs/romfs package or base/updates/dlc bundle found.')
    has_base=any(p.kind==0 for p in packages)
    for p in packages:
        if p.kind==1:p.flags=int(not has_base)
    require(packages,'No content packages found. Empty base folders are skipped.')
    return packages

@dataclass
class FolderIndex:
    root:Path
    packages:list
    directory_stamps:dict
    def validate(self):
        for path,expected in self.directory_stamps.items():
            s=path.lstat()
            require(not stat.S_ISLNK(s.st_mode) and not getattr(s,'st_file_attributes',0)&0x400 and (s.st_mtime_ns,s.st_ino)==expected,'Source folder changed since inspection. Inspect it again.')

def prepare_folder(folder,cancel=None,notify=lambda *a:None):
    root=Path(folder).resolve()
    if root.name.lower() in ('exefs','romfs'):root=root.parent
    stamps={};packages=discover(root,cancel,stamps,notify)
    for p in packages:
        current=root/p.label
        while current.is_relative_to(root):
            if current.is_dir():
                s=current.stat();stamps[current]=(s.st_mtime_ns,s.st_ino)
            if current==root:break
            current=current.parent
    return FolderIndex(root,packages,stamps)

def select_packages(packages,include_kinds=None):
    """Filter before merging; excluded content must never leak into a snapshot."""
    selected=[p for p in packages if include_kinds is None or p.kind in include_kinds]
    require(selected,'No matching packages selected. Include Base, Updates or DLC present in this source.')
    has_base=any(p.kind==0 for p in selected)
    return [replace(p,flags=int(not has_base)) if p.kind==1 else p for p in selected]

def presentation(packages,title='',artwork=None):
    """Override presentation TLVs only; keep original filesystem bytes untouched."""
    title=title.strip()
    require(len(title.encode('utf-8'))<=0x1ff,'Title is too long (maximum 511 UTF-8 bytes).')
    if not title and artwork is None:return packages
    result=[]
    for p in packages:
        # A bundle's custom game cover/title must not rename its separate DLC.
        if p.kind not in (0,1) and any(g.kind in (0,1) for g in packages):result.append(p);continue
        metadata=list(p.metadata)
        if title:
            metadata=[(t,d) for t,d in metadata if t!=5]+[(5,title.encode('utf-8'))]
            original=next((d for t,d in metadata if t==2),None)
            if original is not None and len(original)==0x4000 and not original[0x3215]:
                nacp=bytearray(original)
                for lang in range(16):nacp[lang*0x300:lang*0x300+0x200]=title.encode('utf-8').ljust(0x200,b'\0')
                metadata=[(t,d) for t,d in metadata if t!=2]+[(2,bytes(nacp))]
        if artwork is not None:metadata=[(t,d) for t,d in metadata if t!=3]+[(3,artwork)]
        result.append(replace(p,metadata=metadata))
    return result

def pack_folder(folder,output,latest_snapshot=True,prepared=None,include_kinds=None,title='',artwork=None,**options):
    folder=Path(folder).resolve();output=Path(output).resolve()
    if folder.name.lower() in ('exefs','romfs'):folder=folder.parent
    require(not output.is_relative_to(folder),'Save the NUP outside the source folder.')
    index=prepared if prepared is not None else prepare_folder(folder,options.get('cancel'),options.get('notify',lambda *a:None))
    require(index.root==folder,'Inspected source does not match the selected folder.');index.validate();packages=index.packages
    packages=select_packages(packages,include_kinds)
    before=sum(s.size for p in packages for s in p.files.values())
    if latest_snapshot:packages=compact_packages(packages)
    packages=presentation(packages,title,artwork)
    result=pack(packages,output,source_guard=index.validate,**options)
    result.update(latest_snapshot=bool(latest_snapshot),original_bundle_bytes=before,omitted_version_bytes=before-result['source_size'])
    return result

@contextmanager
def nsp_packages(path,cancel=None,notify=lambda *a:None,deep=True):
    """Only our verified plaintext application/add-on NCA dialect is accepted."""
    path=Path(path);fmt.configure(cancel);vf.checkpoint=lambda:check(cancel)
    source=Source.path(path)
    with path.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mapping:
        try:
            root=vf.Region(mapping);require(bytes(root[:4])==b'PFS0','Expected a plaintext NSP/PFS0 container.')
            ncas=vf.partition(root);parsed={};hashes={}
            for name,region in ncas.items():
                check(cancel);require(len(region)>=0xc00 and bytes(region[0x200:0x204])==b'NCA3' and region[0x204]==0,'Only plaintext NSP-Box NSPs are supported; encrypted/retail content is not supported.')
                require(re.fullmatch(r'[0-9a-f]{32}(?:\.cnmt)?\.nca',name) is not None,'Unsupported NCA filename.')
                if deep:
                    notify('Checking source NCA integrity',1)
                    digest=vf.digest(region);require(name[:32]==digest[:16].hex(),'NCA content hash does not match its name.')
                else:digest=None
                for i in range(4):
                    start,end=vf.u('II',region,0x240+i*16)
                    if not start and not end:continue
                    require(6<=start<end and end*512<=len(region),'NCA section outside container.')
                    header=region[0x400+i*512:0x600+i*512]
                    if header[3]==2:
                        block=vf.u('I',header,0x28)[0];require(0<block<=16*1024*1024,'Unsupported NCA integrity block size.')
                    elif header[3]==3:
                        for j in range(6):require(vf.u('I',header,0x18+j*24+16)[0]<=24,'Unsupported IVFC block size.')
                parsed[name]=vf.nca_sections(region,verify_payload=deep);hashes[name]=digest
            metas=[(n,v) for n,v in parsed.items() if v[1]==1];require(metas,'NSP has no title metadata.')
            packages=[];claimed=set()
            for metaname,(_,_,sections) in metas:
                cnmts=vf.partition(sections[0][1]);require(len(cnmts)==1,'Expected one CNMT per metadata NCA.')
                cnmtname,cnmt=next(iter(cnmts.items()));tid,version,ctype,_,extra,count=vf.u('QIBBHH',cnmt)
                require(ctype in (0x80,0x82),'Only application snapshots and DLC NSPs from NSP Box can be converted.')
                require(vf.digest(cnmt[:-32])==bytes(cnmt[-32:]),'CNMT hash mismatch.')
                files={};dirs=set();claimed.add(metaname)
                def add_files(prefix,views):
                    for name,view in views.items():
                        path_parts(name);key=prefix+'/'+name;require(key not in files,'Duplicate NSP file path.')
                        files[key]=Source(len(view),lambda v=view:SliceRegion(v),validator=source.validate)
                for j in range(count):
                    at=0x20+extra+j*0x38;digest=bytes(cnmt[at:at+32]);name=bytes(cnmt[at+32:at+48]).hex()+'.nca'
                    size=int.from_bytes(bytes(cnmt[at+48:at+54]),'little')
                    require(name in ncas and len(ncas[name])==size and name[:32]==digest[:16].hex() and (not deep or hashes[name]==digest),'CNMT content record mismatch.')
                    require(name not in claimed,'Shared NCA records are unsupported.');claimed.add(name)
                    program_id,content_type,content=parsed[name];require(program_id==tid,'NSP content title ID mismatch.')
                    if content_type==0:
                        add_files('exefs',vf.partition(next(b for k,b in content if k=='pfs')))
                        add_files('romfs',romfs_files(next(b for k,b in content if k=='romfs')))
                        dirs.update(('exefs','romfs'))
                    elif content_type==2:add_files('data/control',romfs_files(content[0][1]))
                    elif content_type==4:add_files('romfs',romfs_files(content[0][1]));dirs.add('romfs')
                    else:raise ValueError('Unsupported NSP content type.')
                files['data/nsp/'+cnmtname]=Source.data(bytes(cnmt))
                if ctype==0x80:require('exefs/main.npdm' in files and 'exefs/main' in files and any(n.startswith('romfs/') for n in files),'NSP does not contain a complete game snapshot.')
                if 'exefs/main.npdm' in files:require(npdm_id(files['exefs/main.npdm'].read_small())==tid,'NPDM/title identity mismatch.')
                packages.append(Package(tid,version,0 if ctype==0x80 else 2,files,dirs,metadata_for(files)))
            require(set(ncas)==claimed,'Unrecognized/unreferenced NCA content; refusing to drop it.')
            source.validate();notify('Plaintext NSP integrity checked' if deep else 'NSP package index ready · full integrity checked during conversion',2)
        except (AssertionError,IndexError,struct.error,StopIteration,RecursionError) as error:
            raise ValueError('Malformed or unsupported plaintext NSP: '+str(error)) from error
        yield packages

class SliceRegion(io.RawIOBase):
    def __init__(self,region):self.region=region;self.pos=0
    def readable(self):return True
    def read(self,n=-1):
        n=len(self.region)-self.pos if n<0 else min(n,len(self.region)-self.pos)
        b=bytes(self.region[self.pos:self.pos+n]);self.pos+=n;return b

def nsp_to_nup(path,output,include_kinds=None,**options):
    require(Path(path).resolve()!=Path(output).resolve(),'Input and output must differ.')
    with nsp_packages(path,options.get('cancel'),options.get('notify',lambda *a:None)) as packages:
        return pack(select_packages(packages,include_kinds),output,**options)

def romfs_files(buf):
    """Bounded RomFS traversal: never follow repeated offsets in imported NSPs."""
    vals=vf.u('10Q',buf);require(vals[0]==0x50,'Invalid RomFS header.')
    dt,ds,ft,fs,data=vals[3],vals[4],vals[7],vals[8],vals[9]
    require(0x50<=dt<=len(buf) and ds<=len(buf)-dt and ft<=len(buf) and fs<=len(buf)-ft and data<=len(buf),'Invalid RomFS table bounds.')
    result={};seen_dirs=set();seen_files=set()
    def visit(off,prefix,depth=0):
        require(depth<256,'RomFS directory nesting is too deep.')
        while off!=0xffffffff:
            check_cancel=vf.checkpoint;check_cancel()
            require(off not in seen_dirs and off+24<=ds,'Cyclic or invalid RomFS directory.');seen_dirs.add(off)
            par,sibling,child,first,hl,n=vf.u('6I',buf,dt+off)
            require(n<=ds-off-24,'RomFS directory name out of bounds.')
            name=bytes(buf[dt+off+24:dt+off+24+n]).decode('utf-8')
            if name:safe_name(name)
            current=prefix+'/'+name if prefix and name else prefix or name
            entry=first
            while entry!=0xffffffff:
                check_cancel();require(entry not in seen_files and entry+32<=fs,'Cyclic or invalid RomFS file.');seen_files.add(entry)
                fp,nextfile,fo,size,fh,fn=vf.u('IIQQII',buf,ft+entry)
                require(fn<=fs-entry-32 and fo<=len(buf)-data and size<=len(buf)-data-fo,'RomFS file out of bounds.')
                name=bytes(buf[ft+entry+32:ft+entry+32+fn]).decode('utf-8');safe_name(name)
                path=current+'/'+name if current else name;require(path not in result,'Duplicate RomFS file.')
                result[path]=buf[data+fo:data+fo+size];entry=nextfile
            if child!=0xffffffff:visit(child,current,depth+1)
            off=sibling
    visit(0,'');return result

def merge_game(packages,selection=None):
    """Eglantine semantics: highest update, whole update ExeFS, RomFS shadowing.

    Lower versions are not cumulatively layered. DLC stays a separate add-on NSP.
    """
    base=next((p for p in packages if p.kind==0),None)
    updates=[p for p in packages if p.kind==1]
    update=max(updates,key=lambda p:p.version) if updates else None
    if selection is not None:
        chosen=packages[selection]
        require(chosen.kind in (0,1),'Selected package is not a game/update.')
        if chosen.kind==0:update=None;base=chosen
        else:update=chosen
    program=base or update;require(program is not None,'No base game or standalone update snapshot found.')
    exefs=update if update and 'exefs/main' in update.files else base
    require(exefs is not None,'No complete ExeFS found.')
    files={n:s for n,s in program.files.items() if not n.startswith(('romfs/','exefs/'))}
    files.update({n:s for n,s in exefs.files.items() if n.startswith('exefs/')})
    if base:files.update({n:s for n,s in base.files.items() if n.startswith('romfs/')})
    if update:
        require(update.title_id&~0x1fff==program.title_id&~0x1fff,'Unrelated game update.')
        files.update({n:s for n,s in update.files.items() if n.startswith('romfs/')})
    require('exefs/main.npdm' in files and 'exefs/main' in files and any(n.startswith('romfs/') for n in files),'Conversion requires a complete game snapshot, not a delta-only update.')
    tid=npdm_id(files['exefs/main.npdm'].read_small());require(tid==program.title_id,'NPDM ID differs from the application ID; conversion would require changing original metadata.')
    for name in files:
        parent=str(Path(name).parent).replace('\\','/')
        while parent!='.':
            require(parent not in files,'Update file/directory collision cannot be represented in NSP.');parent=str(Path(parent).parent).replace('\\','/')
    directories={'exefs','romfs'}
    for p in (program,update):
        if p:
            directories.update(n for n in p.directories if not n.startswith('exefs/') and n not in files)
    directories.update(n for n in exefs.directories if n.startswith('exefs/'))
    metadata=[(t,d) for t,d in program.metadata if t not in (1,7)]
    metadata.append((1,files['exefs/main.npdm'].read_small()))
    with files['exefs/main'].opener() as main:head=main.read(0x60)
    if len(head)==0x60 and (head[:4]==b'NSO0' or head[0x10:0x14]==b'NRO0'):metadata.append((7,head[0x40:0x60]))
    if update:
        display=next((d for t,d in update.metadata if t==4),None)
        if display is not None:metadata=[(t,d) for t,d in metadata if t!=4]+[(4,display)]
    return Package(tid,update.version if update else program.version,0,files,directories,metadata)

def compact_packages(packages):
    """One latest runnable game tree; retain required base-only files and DLC."""
    games=[p for p in packages if p.kind in (0,1)]
    if not games:return packages
    # Preserve a single original base as-is. Bundles/standalone updates become a snapshot.
    if len(games)==1 and games[0].kind==0:return packages
    merged=merge_game(packages)
    return [merged]+[p for p in packages if p.kind not in (0,1)]

def build_snapshot_nsp(package,output,verify=True,notify=lambda *a:None,cancel=None):
    """Rebuild a snapshot, honoring explicit presentation metadata overrides."""
    output=Path(output);require(not output.exists(),'NSP output already exists.')
    fmt.configure(cancel,lambda done,total:notify('Building NSP integrity trees',20+35*done/max(total,1)))
    with tempfile.TemporaryDirectory(prefix='.nup-nsp-',dir=output.parent) as work:
        root=Path(work);total=sum(s.size for s in package.files.values());done=0
        for name,source in package.files.items():
            if not name.startswith(('exefs/','romfs/','data/control/','control/')) and name!='control.nacp':continue
            target=root.joinpath(*path_parts(name));target.parent.mkdir(parents=True,exist_ok=True)
            with source.opener() as f,target.open('xb') as out:
                count=0
                while b:=f.read(1024*1024):check(cancel);out.write(b);count+=len(b);done+=len(b);require(count<=source.size,'Source size changed.');notify('Preparing snapshot',20*done/max(total,1))
            require(count==source.size,'Incomplete snapshot file.');source.validate()
        if package.kind==2:
            from . import dlc
            return dlc.build(dlc.DlcSnapshot(root,package.title_id,package.version,'NUP DLC'),output,verify_output=verify,notify=notify,cancel=cancel)
        control=root/'data/control'
        original=next((d for t,d in package.metadata if t==2),None)
        # Presentation TLVs are authoritative when supplied. Folder packing can
        # override them without modifying the original archived filesystem.
        if original is not None:
            require(len(original)==0x4000,'Original NACP is not a supported 0x4000-byte control record.')
            control.mkdir(parents=True,exist_ok=True);(control/'control.nacp').write_bytes(original)
        if not (control/'control.nacp').is_file():
            control.mkdir(parents=True,exist_ok=True)
            original=next((d for t,d in package.metadata if t==2),None)
            if original is None:
                for p in (root/'control/control.nacp',root/'control.nacp'):
                    if p.is_file():original=p.read_bytes();break
            if original is None:
                title=next((d.decode('utf-8','replace') for t,d in package.metadata if t==5),'NUP game')
                display=next((d.decode('utf-8','replace') for t,d in package.metadata if t==4),'Snapshot')
                entries,_=engine.control_data(engine.Snapshot(root,package.title_id,package.version,'NUP',title),title,display,None)
                original=dict(entries)['control.nacp']
            require(len(original)==0x4000,'Original NACP is not a supported 0x4000-byte control record.')
            (control/'control.nacp').write_bytes(original)
        icon=next((d for t,d in package.metadata if t==3),None)
        if icon is not None:(control/'icon_AmericanEnglish.dat').write_bytes(icon)
        expected_files=dict(package.files)
        if original is not None:expected_files['data/control/control.nacp']=Source.data(original)
        if icon is not None:expected_files['data/control/icon_AmericanEnglish.dat']=Source.data(icon)
        exefs=root/'exefs';romfs=root/'romfs'
        require(exefs.is_dir() and romfs.is_dir(),'Missing complete ExeFS/RomFS snapshot.')
        require(all(p.is_file() for p in exefs.iterdir()),'Nested ExeFS directories are unsupported by NSP.')
        program=fmt.nca([fmt.pfs_section(fmt.filesystem([(p.name,p) for p in sorted(exefs.iterdir())])),fmt.romfs_section(fmt.romfs(romfs,[]))],package.title_id,0,0)
        control_nca=fmt.nca([fmt.romfs_section(fmt.romfs(control,[]))],package.title_id,2,0)
        records=[];entries=[]
        for blob,ctype in ((program,1),(control_nca,3)):
            digest=blob.digest();entries.append((digest[:16].hex()+'.nca',blob));records.append(digest+digest[:16]+blob.size.to_bytes(6,'little')+bytes([ctype,0]))
        cnmt=bytearray(0x20);struct.pack_into('<QIBBHHH',cnmt,0,package.title_id,package.version,0x80,0,16,len(records),0)
        cnmt+=struct.pack('<QII',package.title_id+0x800,0,0)+b''.join(records);cnmt+=fmt.sha(cnmt)
        meta=fmt.nca([fmt.pfs_section(fmt.filesystem([(f'Application_{package.title_id:016x}.cnmt',bytes(cnmt))]))],package.title_id,1,0)
        entries.append((meta.digest()[:16].hex()+'.cnmt.nca',meta));blob=fmt.package(entries,'nsp')
        temp=output.with_name(output.name+'.'+uuid.uuid4().hex[:10]+'.partial')
        try:
            with temp.open('xb') as out:
                done=0
                for b in blob.chunks():check(cancel);out.write(b);done+=len(b);notify('Writing reconstructed NSP',60+25*done/blob.size)
                out.flush();os.fsync(out.fileno())
            if verify:
                with nsp_packages(temp,cancel) as rebuilt:
                    actual=rebuilt[0]
                    for name,source in expected_files.items():
                        if not name.startswith(('exefs/','romfs/','data/control/')):continue
                        require(name in actual.files,'Missing reconstructed source file: '+name)
                        def digest(s):
                            h=hashlib.sha256()
                            with s.opener() as f:
                                while b:=f.read(1024*1024):check(cancel);h.update(b)
                            return h.digest()
                        require(source.size==actual.files[name].size and digest(source)==digest(actual.files[name]),'NSP reconstruction changed expected file: '+name)
            check(cancel);commit_file(temp,output)
            return {'output':str(output),'size':blob.size,'verified':verify}
        finally:
            if temp.exists():temp.unlink()

def nup_to_nsp(path,output,selection=None,verify=True,notify=lambda *a:None,cancel=None,include_kinds=None):
    """Whole archive -> game+highest update and separate DLC NSPs, or one package."""
    output=Path(output).absolute();require(not output.exists(),'Output already exists; choose a new path.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with Archive(path,cancel) as archive:
        archive.verify(lambda s,v:notify(s,v*.1))
        if selection is None:
            selected=select_packages(archive.packages,include_kinds)
            packages=[]
            if any(p.kind in (0,1) for p in selected):packages.append(merge_game(selected))
            # Preserve every distinct DLC version as an independently installable NSP.
            packages.extend(p for p in selected if p.kind==2)
            require(not any(p.kind in (3,4) for p in selected),'Reserved/system packages cannot be converted to NSP.')
        else:
            require(0<=selection<len(archive.packages),'Select a valid package.')
            p=archive.packages[selection]
            packages=[p if p.kind==2 else merge_game(archive.packages,selection)]
        require(packages,'No convertible content packages found.')
        total=sum(s.size for p in packages for s in p.files.values())
        require(shutil.disk_usage(output.parent).free>total*2.1+64*1024*1024,'NSP conversion needs space for a temporary extracted snapshot and the output.')
        require(len(packages)==1 or output.suffix.lower()!='.nsp','A game plus DLC needs a new output folder, not one .nsp filename.')
        single=output.suffix.lower()=='.nsp'
        if single:
            result=build_snapshot_nsp(packages[0],output,verify,notify,cancel);archive.unchanged();notify('NSP ready',100);return result
        stage=Path(tempfile.mkdtemp(prefix='.nup-convert-',dir=output.parent))
        try:
            results=[]
            for i,p in enumerate(packages):
                check(cancel);name=f'{"DLC" if p.kind==2 else "Game"} [{p.title_id:016X}] v{p.version}.nsp'
                result=build_snapshot_nsp(p,stage/name,verify,lambda s,v:notify(s,10+89*(i+v/100)/len(packages)),cancel);results.append(result)
            archive.unchanged();check(cancel);stage.rename(output);notify('NSP conversion complete',100)
            return {'output':str(output),'size':sum(r['size'] for r in results),'verified':verify,'packages':len(results)}
        finally:
            if stage.exists():
                require(stage.resolve().is_relative_to(output.parent.resolve()) and not linked(stage),'Temporary conversion folder changed unexpectedly.')
                shutil.rmtree(stage)

def inspect(path,verify=False,notify=lambda *a:None,cancel=None):
    with Archive(path,cancel) as archive:
        result=archive.inspect()
        if verify:archive.verify(notify)
        result['verified']=verify;result['output']=str(path);result['size']=result['archive_size'];return result
