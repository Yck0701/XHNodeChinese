"""Use the exact MSVC installation selected by UBT's generated response file."""
from pathlib import Path
import re


def checked_path(path):
    value = str(Path(path).resolve())
    if re.search(r'[\r\n"%&|<>!^]', value):
        raise ValueError('编译路径含命令行特殊字符，请将编译目录放到普通路径：' + value)
    return Path(value)


def select_toolchain(response, vcvars_hint='', requested='auto', log=print):
    roots = {}
    sdk_versions = set()
    for line in response.splitlines():
        include = re.match(r'^\s*/(?:external:)?I\s*"([^"]+)"', line, re.I)
        if not include:
            continue
        path = include[1].replace('\\', '/')
        toolset = re.match(r'^(.*?/VC/Tools/MSVC/(\d+\.\d+\.\d+))/include/?$', path, re.I)
        if toolset:
            roots[toolset[1].casefold()] = (Path(toolset[1]), toolset[2])
        sdk = re.search(r'/Windows Kits/10/include/(\d+\.\d+\.\d+\.\d+)/', path, re.I)
        if sdk:
            sdk_versions.add(sdk[1])
    if len(roots) != 1:
        raise ValueError('无法从 UE 生成的编译配置确定唯一 MSVC 工具集。请重新生成配置，并检查 UE 的 C++ 编译环境。')
    root, version = next(iter(roots.values()))
    root = checked_path(root)
    vcvars = root.parents[2] / 'Auxiliary/Build/vcvars64.bat'
    compiler = root / 'bin/Hostx64/x64/cl.exe'
    linker = root / 'bin/Hostx64/x64/link.exe'
    missing = [str(p) for p in (vcvars, compiler, linker) if not p.is_file()]
    if missing:
        raise ValueError('UE 选择的 MSVC ' + version + ' 不完整。请在对应的 Visual Studio Installer 中安装或修复该 C++ x64 工具集。缺少：' + '；'.join(missing))
    if len(sdk_versions) > 1:
        raise ValueError('UE 编译配置引用了多个 Windows SDK 版本，请重新生成编译配置。')
    requested = str(requested).strip()
    if requested not in ('', 'auto') and not (version == requested or version.startswith(requested + '.')):
        log('管理器填写的 MSVC ' + requested + ' 与 UE 编译配置不一致；跟随 UE 使用 ' + version + '。')
    if vcvars_hint and Path(vcvars_hint).resolve() != vcvars:
        log('使用 UE 所选 MSVC 对应的 Visual Studio 环境：' + str(vcvars))
    log('已确认 MSVC ' + version + '：' + str(compiler))
    sdk_version = next(iter(sdk_versions), '')
    if sdk_version:
        log('Windows SDK：' + sdk_version)
    return dict(root=root, version=version, vcvars=vcvars, compiler=compiler, sdk_version=sdk_version)


def build_command(toolchain, response):
    vcvars = checked_path(toolchain['vcvars'])
    compiler = checked_path(toolchain['compiler'])
    response = checked_path(response)
    version = toolchain['version']
    sdk = toolchain['sdk_version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or (sdk and not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', sdk)):
        raise ValueError('编译器或 Windows SDK 版本无效。')
    return ('@echo off\nsetlocal\nchcp 65001 >nul\n'
            'call "' + str(vcvars) + '" ' + sdk + ' -vcvars_ver=' + version + '\n'
            'if errorlevel 1 (\n'
            'echo [XH ERROR] Visual Studio environment initialization failed. Repair the selected C++ toolset and Windows SDK.\n'
            'exit /b 1\n)\n'
            'if /I not "%VCToolsInstallDir%bin\\Hostx64\\x64\\cl.exe"=="' + str(compiler) + '" (\n'
            'echo [XH ERROR] Visual Studio did not initialize the MSVC toolset selected by UE. Repair the selected C++ toolset.\n'
            'exit /b 1\n)\n'
            '"' + str(compiler) + '" @"' + str(response) + '"\n'
            'exit /b %errorlevel%\n')
