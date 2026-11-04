#!/usr/bin/env python3
"""Install/upgrade/uninstall without changing Codex configuration."""
import argparse
from pathlib import Path
import shutil
import sys
import uuid

NAME='zzzplus-imagegen'


def main():
    parser=argparse.ArgumentParser(description='跨平台 Skill 安装、升级及安全卸载（保留备份）')
    parser.add_argument('action',choices=['install','uninstall'])
    parser.add_argument('--target',type=Path,default=Path.home()/'.agents/skills',help='skills 父目录，而非 Skill 本身')
    parser.add_argument('--upgrade',action='store_true')
    args=parser.parse_args()
    source=Path(__file__).resolve().parents[1]
    root=args.target.expanduser().absolute()
    dest=root/NAME
    try:
        if root.is_symlink() or dest.is_symlink(): raise ValueError('拒绝操作符号链接目标。')
        root=root.resolve(); dest=root/NAME
        if source==dest or source in dest.parents or dest in source.parents:
            raise ValueError('安装来源和目标不能互相包含。')
        if args.action=='uninstall' and not dest.exists(): raise ValueError('目标未安装。')
        if dest.exists():
            skill=dest/'SKILL.md'
            if not skill.is_file() or 'name: zzzplus-imagegen' not in skill.read_text(encoding='utf-8'):
                raise ValueError('目标不是可识别的 zzzplus-imagegen；不会移动其他文件夹。')
            if args.action=='install' and not args.upgrade:
                raise ValueError('目标已存在；升级请使用 --upgrade，原版会被保留备份。')
        if args.action=='install':
            root.mkdir(parents=True,exist_ok=True)
            staging=root/('.zzzplus-staging-'+uuid.uuid4().hex)
            if any(p.is_symlink() for p in source.rglob('*')): raise ValueError('分发源不得包含符号链接。')
            shutil.copytree(source,staging,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git','generated-images'))
        backup=None
        if dest.exists():
            backup_root=root.parent/'skill-backups'
            if backup_root.is_symlink(): raise ValueError('备份目录不能为符号链接。')
            backup_root.mkdir(parents=True,exist_ok=True)
            backup=backup_root/(NAME+'-'+uuid.uuid4().hex)
            dest.rename(backup)
            print('BACKUP_PATH='+str(backup))
        if args.action=='install':
            try: staging.rename(dest)
            except OSError:
                if backup and not dest.exists(): backup.rename(dest)
                raise
            print('INSTALLED_PATH='+str(dest))
        else: print('已从发现目录移出，备份保留；没有删除图片或修改 Codex 配置。')
        print('请重新打开 Codex 会话。')
        return 0
    except (OSError,ValueError) as exc:
        print('安装操作失败：'+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
