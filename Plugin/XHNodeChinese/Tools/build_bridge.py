"""Rebuild the display bridge using target headers and a complete UE SDK.

Run verify_bridge.py and verify_niagara.py in an isolated TARGET editor before
deploying a rebuilt binary. Fingerprints limit loading; they do not prove ABI.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

p=argparse.ArgumentParser()
p.add_argument('--engine',required=True,help='Target Engine directory')
p.add_argument('--sdk',required=True,help='Complete, corresponding Engine SDK directory')
p.add_argument('--vcvars',required=True,help='VS vcvars64.bat')
p.add_argument('--compiler-version',default='14.50')
p.add_argument('--configuration-dir',help='Reuse a UBT-generated BridgeBuild Development directory')
args=p.parse_args()
plugin=Path(__file__).resolve().parents[1]
engine=Path(args.engine).resolve();sdk=Path(args.sdk).resolve()
out=plugin/'Intermediate/SlateBridge';out.mkdir(parents=True,exist_ok=True)
# Accessed Niagara layouts must match the SDK used for generated dependencies.
# Engine dependency-only headers may differ; these concrete action/widget types may not.
for relative in (
    'Plugins/FX/Niagara/Source/NiagaraEditor/Public/Widgets/SNiagaraParameterPanel.h',
    'Plugins/FX/Niagara/Source/NiagaraEditor/Public/NiagaraParameterPanelTypes.h',
    'Plugins/FX/Niagara/Source/NiagaraEditor/Public/NiagaraScriptVariable.h',
    'Plugins/FX/Niagara/Source/NiagaraEditor/Public/NiagaraEditorSettings.h',
    'Source/Runtime/Slate/Public/Framework/Application/SlateUser.h',
    'Source/Editor/GraphEditor/Public/SGraphActionMenu.h',
    'Source/Runtime/Engine/Classes/EdGraph/EdGraphSchema.h',
    'Plugins/FX/Niagara/Source/NiagaraEditor/Public/NiagaraActions.h',
    'Plugins/FX/Niagara/Source/NiagaraEditor/Public/Widgets/SItemSelector.h',
    'Plugins/FX/Niagara/Source/NiagaraEditor/Public/Config/NiagaraFavoriteActionsConfig.h',
    'Plugins/FX/Niagara/Source/Niagara/Public/NiagaraTypes.h',
    'Plugins/FX/Niagara/Source/NiagaraEditorWidgets/Private/Stack/SNiagaraStackItemGroupAddMenu.h',
):
    if (engine/relative).read_bytes()!=(sdk/relative).read_bytes():
        raise RuntimeError('Accessed SDK header mismatch; use matching generated headers: '+relative)
if args.configuration_dir:
    configured=Path(args.configuration_dir).resolve()
else:
    package=plugin/'Intermediate/CompilerConfiguration'
    subprocess.run(['cmd.exe','/d','/c',str(sdk/'Build/BatchFiles/RunUAT.bat'),
        'BuildPlugin','-Plugin='+str(plugin/'Tools/CompilerHost/BridgeBuild.uplugin'),
        '-Package='+str(package),'-TargetPlatforms=Win64','-NoDeleteHostProject'],check=True)
    configured=package/'HostProject/Plugins/BridgeBuild/Intermediate/Build/Win64/x64/UnrealEditor/Development/BridgeBuild'
lines=[]
for line in (configured/'BridgeBuild.Shared.rsp').read_text(encoding='utf-8-sig').splitlines():
    if line in ('/c','/X') or line.startswith(('/we','/W4')):continue
    if line.startswith(('/I ', '/external:I ')):
        original=line.split('"')[1];path=Path(original)
        if path.is_absolute() and path.is_relative_to(sdk):
            relative=path.relative_to(sdk)
            candidate=engine/relative
            if candidate.exists():path=candidate
        if not path.is_absolute():
            path=(engine/'Source'/path).resolve()
            if not path.exists():
                if original.startswith(('../Intermediate','ThirdParty')) or '/Intermediate/' in original.replace('\\','/'):
                    path=(sdk/'Source'/original).resolve()
                else:raise FileNotFoundError(path)
        # The custom distribution omits Engine generated headers and some public
        # dependencies. Use the SDK's matched Engine header/generated pair for
        # these dependency-only types; Slate and Niagara layouts remain target headers.
        if path.is_relative_to(engine/'Source/Runtime/Engine'):
            path=sdk/path.relative_to(engine)
        line=line.split('"')[0]+'"'+str(path)+'"'
    lines.append(line)
fallbacks=[]
for line in lines:
    if line.startswith(('/I ', '/external:I ')):
        path=Path(line.split('"')[1])
        if path.is_relative_to(engine):
            candidate=sdk/path.relative_to(engine)
            if candidate.exists():fallbacks.append('/I "'+str(candidate)+'"')
lines += fallbacks
lines += ['/I "'+str(engine/'Plugins/FX/Niagara/Source/NiagaraEditorWidgets/Private')+'"']
lines += ['/std:c++20','/GR-','/LD','/W0','/FI"'+str(configured/'Definitions.h')+'"',
    '"'+str(plugin/'Source/SlateBridge/Bridge.cpp')+'"','/Fo"'+str(out/'Bridge.obj')+'"',
    '/Fe"'+str(out/'XHSlateBridge.dll')+'"','/link','/INCREMENTAL:NO']
for mod in ('Core','CoreUObject','Slate','SlateCore','ApplicationCore','InputCore','RenderCore','RHI','TraceLog'):
    lines.append('"'+str(sdk/f'Intermediate/Build/Win64/x64/UnrealEditor/Development/{mod}/UnrealEditor-{mod}.lib')+'"')
for mod in ('NiagaraEditor','NiagaraEditorWidgets','Niagara','NiagaraCore'):
    lines.append('"'+str(sdk/f'Plugins/FX/Niagara/Intermediate/Build/Win64/x64/UnrealEditor/Development/{mod}/UnrealEditor-{mod}.lib')+'"')
for mod in ('Engine','UnrealEd','GraphEditor','Projects'):
    lines.append('"'+str(sdk/f'Intermediate/Build/Win64/x64/UnrealEditor/Development/{mod}/UnrealEditor-{mod}.lib')+'"')
rsp=out/'compile.rsp';rsp.write_text('\n'.join(lines),encoding='utf-8')
cmd=out/'build.cmd';cmd.write_text('@echo off\ncall "'+str(Path(args.vcvars).resolve())+'" -vcvars_ver='+args.compiler_version+'\nif errorlevel 1 exit /b %errorlevel%\ncl @"'+str(rsp)+'"\n',encoding='utf-8')
subprocess.run(['cmd.exe','/d','/c',str(cmd)],cwd=out,check=True)
dest=plugin/'Binaries/Win64';dest.mkdir(parents=True,exist_ok=True)
bridge_file='XHSlateBridge0213.dll'
shutil.copy2(out/'XHSlateBridge.dll',dest/bridge_file)
files=[f'Binaries/Win64/UnrealEditor-{mod}.dll' for mod in ('Core','CoreUObject','Slate','SlateCore','ApplicationCore','InputCore','Engine','GraphEditor')]
files += [f'Plugins/FX/Niagara/Binaries/Win64/UnrealEditor-{mod}.dll' for mod in ('NiagaraEditor','NiagaraEditorWidgets','Niagara','NiagaraCore')]
manifest={'engine_sha256':{name:hashlib.sha256((engine/name).read_bytes()).hexdigest() for name in files},
    'bridge_file':bridge_file,
    'bridge_sha256':hashlib.sha256((dest/bridge_file).read_bytes()).hexdigest()}
(dest/'bridge-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('Build succeeded. Run isolated target-engine verification before deployment.')

# The read-only module scanner is a separate DLL, allowing Python updates to
# deploy it without unloading Slate bindings in a running editor.
index_rsp=out/'module-index.rsp'
index_lines=[line.replace(str(plugin/'Source/SlateBridge/Bridge.cpp'),str(plugin/'Source/SlateBridge/ModuleIndex.cpp'))
    .replace(str(out/'Bridge.obj'),str(out/'ModuleIndex.obj'))
    .replace(str(out/'XHSlateBridge.dll'),str(out/'XHModuleIndex030_2.dll')) for line in lines]
index_rsp.write_text('\n'.join(index_lines),encoding='utf-8')
index_cmd=out/'build-module-index.cmd'
index_cmd.write_text(cmd.read_text(encoding='utf-8').replace(str(rsp),str(index_rsp)),encoding='utf-8')
subprocess.run(['cmd.exe','/d','/c',str(index_cmd)],cwd=out,check=True)
index_dest=dest/'XHModuleIndex030_2.dll';shutil.copy2(out/index_dest.name,index_dest)
index_manifest=dict(manifest,bridge_file=index_dest.name,bridge_sha256=hashlib.sha256(index_dest.read_bytes()).hexdigest())
(dest/'module-index-manifest.json').write_text(json.dumps(index_manifest,indent=2),encoding='utf-8')
