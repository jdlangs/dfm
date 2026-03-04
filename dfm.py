import dataclasses
import filecmp
import os
import pathlib

import click
import yaml
from rich.console import Console

console = Console()


@dataclasses.dataclass
class Mapping:
    name: str
    source: str
    dest: str


class Mappings:
    def __init__(self, cfg_dir: pathlib.Path, data: dict):
        self._mappings = list()
        for (s,d) in data.items():
            ls = cfg_dir / s
            hd = os.path.expanduser(os.path.join("~", d))
            self._mappings.append(Mapping(s,ls,hd))

    def items(self):
        for item in self._mappings:
            yield item

    @classmethod
    def from_yaml(cls, filename: pathlib.Path):
        with open(filename) as fs:
            idata = yaml.safe_load(fs)
            return cls(filename.parent, idata)


def exists(m: Mapping):
    if os.path.exists(m.dest):
        return True
    else:
        return False


def clear(m: Mapping, *, dry_run: bool = False):
    if dry_run:
        console.print(f'{m.name}: Remove destination file: {m.dest}', style="yellow")
        return

    i = input(f'{m.name}: Remove destination file: {m.dest} ? (y/N)')
    if i == 'y':
        os.remove(m.dest)
        return True
    else:
        return False


def has_diff(m: Mapping):
    if filecmp.cmp(m.source, m.dest):
        return False
    else:
        return True


def linkfile(m: Mapping, *, dry_run: bool=False):
    console.print(f'{m.name}: linking {m.dest} -> {m.source}', style="yellow")
    if dry_run:
        return

    dest = pathlib.Path(m.dest)
    if not dest.parent.exists():
        dest.parent.mkdir(parents=True)
    os.symlink(m.source, m.dest)


def load_mappings(cfg_dir: pathlib.Path):
    input_file = cfg_dir / 'files.yaml'
    if not input_file.exists():
        raise click.ClickException(f"'files.yaml' not found in '{cfg_dir}'")
    return Mappings.from_yaml(input_file)


@click.group()
@click.option("-C", "--dir", type=click.Path(exists=True, file_okay=False, path_type=pathlib.Path), default=os.getcwd(), help="Directory with files.yaml mappings list.")
@click.pass_context
def main(ctx, dir):
    """DotFile Manager"""
    ctx.ensure_object(dict)
    ctx.obj["dir"] = dir


@main.command()
@click.option("-n", "--dry-run", is_flag=True, help="Only print actions to be taken")
@click.pass_context
def sync(ctx, dry_run):
    """Sync symlinks from files.yaml mappings."""
    cfg_dir = ctx.obj["dir"]
    maps = load_mappings(cfg_dir)
    for m in maps.items():
        if exists(m):
            if has_diff(m):
                console.print(f'{m.name}: Different file already exists at: {m.dest}', style="red")
                if clear(m, dry_run=dry_run):
                    linkfile(m, dry_run=dry_run)
            else:
                console.print(f'{m.name}: Up to date', style="green")
        else:
            linkfile(m, dry_run=dry_run)


if __name__ == "__main__":
    main()
