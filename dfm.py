import dataclasses
import filecmp
import os
import pathlib
import shutil
import subprocess

import click
from click.shell_completion import CompletionItem
import git
import yaml
from rich.console import Console
from rich.table import Table

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
        console.print(f'{m.name}: Different file exists at {m.dest}, would replace with symlink', style="yellow")
        return

    choice = click.prompt(
        f'{m.name}: Different file exists at {m.dest}. [r]eplace / [b]ackup & replace / [s]kip',
        type=click.Choice(['r', 'b', 's'], case_sensitive=False),
        default='s',
    )
    if choice == 'r':
        os.remove(m.dest)
        return True
    elif choice == 'b':
        backup = m.dest + ".bak"
        shutil.move(m.dest, backup)
        console.print(f"[green]Backed up:[/green] {m.dest} -> {backup}")
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


DEFAULT_DOTFILES = pathlib.Path.home() / ".dotfiles"


def resolve_cfg_dir(explicit_dir):
    """Resolve the dotfiles directory: explicit flag > cwd > ~/.dotfiles."""
    if explicit_dir is not None:
        return explicit_dir
    cwd = pathlib.Path.cwd()
    if (cwd / "files.yaml").exists():
        return cwd
    if (DEFAULT_DOTFILES / "files.yaml").exists():
        return DEFAULT_DOTFILES
    raise click.ClickException(
        f"'files.yaml' not found in '{cwd}' or '{DEFAULT_DOTFILES}'"
    )


def load_mappings(cfg_dir: pathlib.Path):
    input_file = cfg_dir / 'files.yaml'
    if not input_file.exists():
        raise click.ClickException(f"'files.yaml' not found in '{cfg_dir}'")
    return Mappings.from_yaml(input_file)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-C", "--dir", type=click.Path(exists=True, file_okay=False, path_type=pathlib.Path), default=None, help="Dotfiles directory (default: cwd, then ~/.dotfiles).")
@click.option("--no-git", is_flag=True, help="Skip git commit and push.")
@click.option("-n", "--dry-run", is_flag=True, help="Only print actions to be taken")
@click.pass_context
def main(ctx, dir, no_git, dry_run):
    """DotFile Manager"""
    ctx.ensure_object(dict)
    ctx.obj["dir"] = resolve_cfg_dir(dir)
    ctx.obj["no_git"] = no_git
    ctx.obj["dry_run"] = dry_run


@main.command()
@click.pass_context
def sync(ctx):
    """Pull latest changes and sync symlinks from files.yaml mappings."""
    dry_run = ctx.obj["dry_run"]
    cfg_dir = ctx.obj["dir"]

    if not ctx.obj["no_git"]:
        try:
            repo = git.Repo(cfg_dir)
            if dry_run:
                console.print("[yellow]Would pull[/yellow] from origin")
            else:
                origin = repo.remotes.origin
                origin.pull()
                console.print("[green]Pulled[/green] from origin")
        except (git.InvalidGitRepositoryError, ValueError, AttributeError):
            pass
        except git.GitCommandError as e:
            console.print(f"[yellow]Warning:[/yellow] Pull failed: {e}")

    maps = load_mappings(cfg_dir)
    for m in maps.items():
        if exists(m):
            if has_diff(m):
                console.print(f'{m.name}: Local file differs from repo version', style="red")
                if clear(m, dry_run=dry_run):
                    linkfile(m, dry_run=dry_run)
            else:
                console.print(f'{m.name}: Up to date', style="green")
        else:
            linkfile(m, dry_run=dry_run)


def classify_link(m: Mapping):
    """Classify the link status of a mapping."""
    dest = pathlib.Path(m.dest)
    if dest.is_symlink():
        if not dest.exists():
            return "broken", "red"
        return "✔", "green"
    if dest.exists():
        return "unlinked", "yellow"
    return "missing", "red"


@main.command()
@click.pass_context
def status(ctx):
    """Show status of all managed dotfiles."""
    cfg_dir = ctx.obj["dir"]
    maps = load_mappings(cfg_dir)
    home = pathlib.Path.home()

    console.print(f"Repo: [bold]{cfg_dir}[/bold]")
    console.print()

    try:
        repo = git.Repo(cfg_dir)
    except git.InvalidGitRepositoryError:
        raise click.ClickException(f"'{cfg_dir}' is not a git repository")

    # Build set of repo-relative paths that have uncommitted changes
    changed_files = set()
    for diff in repo.index.diff(None):
        changed_files.add(diff.a_path)
    for diff in repo.index.diff("HEAD"):
        changed_files.add(diff.a_path)
    for path in repo.untracked_files:
        changed_files.add(path)

    table = Table(box=None, pad_edge=False)
    table.add_column("Link")
    table.add_column("Repo")
    table.add_column("File")
    table.add_column("Source")

    for m in maps.items():
        link_status, link_style = classify_link(m)
        dest_display = f"~/{pathlib.Path(m.dest).relative_to(home)}"
        link_cell = f"[{link_style}]{link_status}[/{link_style}]"

        if m.name in changed_files:
            repo_cell = "[yellow]modified[/yellow]"
        else:
            repo_cell = "[green]✔[/green]"

        table.add_row(link_cell, repo_cell, dest_display, m.name)

    console.print(table)


def open_repo(cfg_dir: pathlib.Path):
    """Open a git repo, erroring if not a repo or if there are dirty files."""
    try:
        repo = git.Repo(cfg_dir)
    except git.InvalidGitRepositoryError:
        raise click.ClickException(f"'{cfg_dir}' is not a git repository")
    if repo.is_dirty() or repo.untracked_files:
        raise click.ClickException(
            f"Dotfiles repo has uncommitted changes. Commit or stash them first."
        )
    return repo


def commit_and_push(cfg_dir: pathlib.Path, paths: list[str], message: str, *, check_clean: bool = True):
    """Stage paths, commit, and push to origin."""
    if check_clean:
        repo = open_repo(cfg_dir)
    else:
        try:
            repo = git.Repo(cfg_dir)
        except git.InvalidGitRepositoryError:
            raise click.ClickException(f"'{cfg_dir}' is not a git repository")

    repo.index.add(paths)
    repo.index.commit(message)
    console.print(f"[green]Committed:[/green] {message}")

    try:
        origin = repo.remotes.origin
    except (ValueError, AttributeError):
        console.print("[yellow]Warning:[/yellow] No remote 'origin' found, skipping push")
        return

    try:
        push_info = origin.push()
        if push_info and any(info.flags & info.ERROR for info in push_info):
            console.print(f"[yellow]Warning:[/yellow] Push failed: {push_info[0].summary}")
        else:
            console.print("[green]Pushed[/green] to origin")
    except git.GitCommandError as e:
        console.print(f"[yellow]Warning:[/yellow] Push failed: {e}")


def remove_from_files_yaml(cfg_dir: pathlib.Path, repo_path: str):
    """Remove an entry from files.yaml by its repo-relative key."""
    files_yaml = cfg_dir / "files.yaml"
    with open(files_yaml) as f:
        data = yaml.safe_load(f) or {}
    data.pop(repo_path, None)
    with open(files_yaml, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


def resolve_file_arg(file: pathlib.Path):
    """Expand and normalize a file path argument to absolute."""
    file = file.expanduser()
    if not file.is_absolute():
        file = pathlib.Path.cwd() / file
    return pathlib.Path(os.path.normpath(file))


def lookup_mapping(cfg_dir: pathlib.Path, home_rel: str):
    """Look up a repo-relative path in files.yaml by its home-relative destination."""
    files_yaml = cfg_dir / "files.yaml"
    if not files_yaml.exists():
        raise click.ClickException(f"'files.yaml' not found in '{cfg_dir}'")
    with open(files_yaml) as f:
        data = yaml.safe_load(f) or {}
    for k, v in data.items():
        if v == home_rel:
            return k
    raise click.ClickException(f"No entry found in files.yaml for: {home_rel}")


def commit_prefix(repo_paths: list[str]):
    """Derive the commit prefix from repo paths (top-level directory or filename)."""
    prefixes = set()
    for rp in repo_paths:
        parts = pathlib.PurePosixPath(rp).parts
        prefixes.add(parts[0] if len(parts) > 1 else rp)
    if len(prefixes) == 1:
        return prefixes.pop()
    return "dotfiles"


def generate_commit_message(cfg_dir: pathlib.Path, repo_paths: list[str]):
    """Generate a commit message, using Claude CLI if available."""
    prefix = commit_prefix(repo_paths)
    repo = git.Repo(cfg_dir)
    diff_output = "\n".join(repo.git.diff(rp) for rp in repo_paths)

    if diff_output and shutil.which("claude"):
        try:
            prompt = (
                "Write a concise one-line git commit message for this dotfile change. "
                f"Use the format: '{prefix}: <short description>'. "
                "No quotes, no explanation, just the message.\n\n"
                f"{diff_output}"
            )
            result = subprocess.run(
                ["claude", "-p", "--model", "haiku", prompt],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Fallback
    if len(repo_paths) == 1:
        return f"{prefix}: update {pathlib.PurePosixPath(repo_paths[0]).name}"
    return f"{prefix}: update {len(repo_paths)} files"


def complete_managed_files(ctx, param, incomplete):
    """Shell completion for managed dotfile paths."""
    try:
        cfg_dir = resolve_cfg_dir(ctx.params.get("dir"))
        maps = load_mappings(cfg_dir)
    except Exception:
        return []

    home = pathlib.Path.home()
    completions = []
    for m in maps.items():
        dest = f"~/{pathlib.Path(m.dest).relative_to(home)}"
        if dest.startswith(incomplete) or m.dest.startswith(incomplete):
            completions.append(CompletionItem(dest))
    return completions


def append_to_files_yaml(cfg_dir: pathlib.Path, repo_path: str, home_rel: str):
    """Append a new entry to files.yaml."""
    files_yaml = cfg_dir / "files.yaml"
    with open(files_yaml, "a") as f:
        f.write(f'"{repo_path}": "{home_rel}"\n')


@main.command()
@click.argument("file", type=click.Path(path_type=pathlib.Path))
@click.option("--repo-path", default=None, help="Where to place the file inside the repo. Default: auto-derived.")
@click.pass_context
def adopt(ctx, file, repo_path):
    """Adopt an existing dotfile into the repo."""
    dry_run = ctx.obj["dry_run"]
    cfg_dir = ctx.obj["dir"]
    home = pathlib.Path.home()
    file = resolve_file_arg(file)

    # Validate
    if file.is_symlink():
        raise click.ClickException(f"File is already a symlink (already managed?): {file}")
    if not file.exists():
        raise click.ClickException(f"File does not exist: {file}")
    if not file.is_file():
        raise click.ClickException(f"Not a regular file: {file}")
    if not str(file).startswith(str(home)):
        raise click.ClickException(f"File is not under home directory: {file}")

    # Compute home-relative path (for files.yaml value)
    home_rel = str(file.relative_to(home))

    # Compute repo-relative path
    if repo_path is None:
        # ~/.config/foo/bar -> foo/bar (skip .config prefix)
        # ~/.other -> other (strip leading dot)
        config_prefix = ".config" + os.sep
        if home_rel.startswith(config_prefix):
            repo_path = home_rel[len(config_prefix):]
        else:
            repo_path = home_rel.lstrip(".")
    repo_dest = cfg_dir / repo_path

    # Check for conflicts
    if repo_dest.exists():
        raise click.ClickException(f"File already exists in repo: {repo_dest}")

    # Check files.yaml for duplicates
    files_yaml = cfg_dir / "files.yaml"
    if files_yaml.exists():
        with open(files_yaml) as f:
            existing = yaml.safe_load(f) or {}
        if repo_path in existing:
            raise click.ClickException(f"Entry already in files.yaml: {repo_path}")
        if home_rel in existing.values():
            raise click.ClickException(f"Destination already in files.yaml: {home_rel}")

    # Check repo is clean before making changes
    if not ctx.obj["no_git"]:
        open_repo(cfg_dir)

    if dry_run:
        console.print(f"[yellow]Would move:[/yellow] {file} -> {repo_dest}")
        console.print(f"[yellow]Would add to files.yaml:[/yellow] \"{repo_path}\": \"{home_rel}\"")
        console.print(f"[yellow]Would symlink:[/yellow] {file} -> {repo_dest}")
        if not ctx.obj["no_git"]:
            console.print(f"[yellow]Would commit:[/yellow] Adopt {home_rel}")
            console.print(f"[yellow]Would push[/yellow] to origin")
        return

    # Move file into repo
    repo_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(file), str(repo_dest))
    console.print(f"[green]Moved:[/green] {file} -> {repo_dest}")

    # Update files.yaml
    append_to_files_yaml(cfg_dir, repo_path, home_rel)
    console.print(f"[green]Added to files.yaml:[/green] \"{repo_path}\": \"{home_rel}\"")

    # Create symlink
    m = Mapping(repo_path, str(repo_dest), str(file))
    linkfile(m)

    # Git commit and push
    if not ctx.obj["no_git"]:
        commit_and_push(cfg_dir, [repo_path, "files.yaml"], f"Adopt {home_rel}")


@main.command()
@click.argument("file", type=click.Path(path_type=pathlib.Path), shell_complete=complete_managed_files)
@click.option("-r", "--rm", is_flag=True, help="Delete the file entirely instead of copying it back")
@click.pass_context
def drop(ctx, file, rm):
    """Remove a dotfile from repo management, copying it back to its original location."""
    dry_run = ctx.obj["dry_run"]
    cfg_dir = ctx.obj["dir"]
    home = pathlib.Path.home()
    file = resolve_file_arg(file)

    if not str(file).startswith(str(home)):
        raise click.ClickException(f"File is not under home directory: {file}")

    home_rel = str(file.relative_to(home))
    repo_path = lookup_mapping(cfg_dir, home_rel)
    repo_source = cfg_dir / repo_path

    if not repo_source.exists():
        raise click.ClickException(f"Source file not found in repo: {repo_source}")

    # Check repo is clean before making changes
    if not ctx.obj["no_git"]:
        open_repo(cfg_dir)

    if dry_run:
        if file.is_symlink() or file.exists():
            console.print(f"[yellow]Would remove:[/yellow] {file}")
        if not rm:
            console.print(f"[yellow]Would copy:[/yellow] {repo_source} -> {file}")
        console.print(f"[yellow]Would remove from repo:[/yellow] {repo_source}")
        console.print(f"[yellow]Would remove from files.yaml:[/yellow] {repo_path}")
        if not ctx.obj["no_git"]:
            console.print(f"[yellow]Would commit:[/yellow] Drop {home_rel}")
            console.print(f"[yellow]Would push[/yellow] to origin")
        return

    # Remove symlink/file if it exists
    if file.is_symlink() or file.exists():
        file.unlink()
        console.print(f"[green]Removed:[/green] {file}")

    # Copy repo file back to original location (unless --rm)
    if not rm:
        file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(repo_source), str(file))
        console.print(f"[green]Copied:[/green] {repo_source} -> {file}")

    # Remove from repo
    repo_source.unlink()
    console.print(f"[green]Removed from repo:[/green] {repo_source}")

    # Clean up empty parent directories in repo
    parent = repo_source.parent
    while parent != cfg_dir:
        if not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
        else:
            break

    # Remove from files.yaml
    remove_from_files_yaml(cfg_dir, repo_path)
    console.print(f"[green]Removed from files.yaml:[/green] {repo_path}")

    # Git commit and push
    if not ctx.obj["no_git"]:
        repo = git.Repo(cfg_dir)
        repo.index.remove([repo_path])
        repo.index.add(["files.yaml"])
        repo.index.commit(f"Drop {home_rel}")
        console.print(f"[green]Committed:[/green] Drop {home_rel}")

        try:
            origin = repo.remotes.origin
        except (ValueError, AttributeError):
            console.print("[yellow]Warning:[/yellow] No remote 'origin' found, skipping push")
            return

        try:
            push_info = origin.push()
            if push_info and any(info.flags & info.ERROR for info in push_info):
                console.print(f"[yellow]Warning:[/yellow] Push failed: {push_info[0].summary}")
            else:
                console.print("[green]Pushed[/green] to origin")
        except git.GitCommandError as e:
            console.print(f"[yellow]Warning:[/yellow] Push failed: {e}")


@main.command()
@click.argument("file", type=click.Path(path_type=pathlib.Path), required=False, default=None, shell_complete=complete_managed_files)
@click.pass_context
def diff(ctx, file):
    """Show the git diff of managed dotfiles. If FILE is given, show only that file."""
    cfg_dir = ctx.obj["dir"]

    try:
        repo = git.Repo(cfg_dir)
    except git.InvalidGitRepositoryError:
        raise click.ClickException(f"'{cfg_dir}' is not a git repository")

    if file is not None:
        home = pathlib.Path.home()
        file = resolve_file_arg(file)
        if not str(file).startswith(str(home)):
            raise click.ClickException(f"File is not under home directory: {file}")
        home_rel = str(file.relative_to(home))
        repo_path = lookup_mapping(cfg_dir, home_rel)
        diff_output = repo.git.diff(repo_path)
    else:
        diff_output = repo.git.diff()

    if diff_output:
        click.echo(diff_output)
    else:
        console.print("[green]No changes[/green]")


@main.command()
@click.argument("files", type=click.Path(path_type=pathlib.Path), nargs=-1, required=True, shell_complete=complete_managed_files)
@click.option("-m", "--message", default=None, help="Commit message. Default: auto-generated.")
@click.pass_context
def commit(ctx, files, message):
    """Commit changes to managed dotfiles."""
    dry_run = ctx.obj["dry_run"]
    cfg_dir = ctx.obj["dir"]
    home = pathlib.Path.home()

    repo_paths = []
    for file in files:
        file = resolve_file_arg(file)
        if not str(file).startswith(str(home)):
            raise click.ClickException(f"File is not under home directory: {file}")
        home_rel = str(file.relative_to(home))
        repo_paths.append(lookup_mapping(cfg_dir, home_rel))

    if message is None:
        message = generate_commit_message(cfg_dir, repo_paths)

    if dry_run:
        for rp in repo_paths:
            console.print(f"[yellow]Would stage:[/yellow] {rp}")
        console.print(f"[yellow]Would commit:[/yellow] {message}")
        console.print(f"[yellow]Would push[/yellow] to origin")
        return

    commit_and_push(cfg_dir, repo_paths, message, check_clean=False)


@main.command()
@click.argument("files", type=click.Path(path_type=pathlib.Path), nargs=-1, shell_complete=complete_managed_files)
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def reset(ctx, files, yes):
    """Reset modified dotfiles to the last committed version. Resets all changes if no files given."""
    dry_run = ctx.obj["dry_run"]
    cfg_dir = ctx.obj["dir"]
    home = pathlib.Path.home()

    try:
        repo = git.Repo(cfg_dir)
    except git.InvalidGitRepositoryError:
        raise click.ClickException(f"'{cfg_dir}' is not a git repository")

    if files:
        repo_paths = []
        for file in files:
            file = resolve_file_arg(file)
            if not str(file).startswith(str(home)):
                raise click.ClickException(f"File is not under home directory: {file}")
            home_rel = str(file.relative_to(home))
            repo_paths.append(lookup_mapping(cfg_dir, home_rel))
    else:
        # Reset everything that has changes
        repo_paths = [d.a_path for d in repo.index.diff(None)]
        if not repo_paths:
            console.print("[green]No changes to reset[/green]")
            return

    for rp in repo_paths:
        if dry_run:
            console.print(f"[yellow]Would reset:[/yellow] {rp}")
            continue

        if not yes and not click.confirm(f"Reset {rp}?"):
            continue

        repo.git.checkout("--", rp)
        console.print(f"[green]Reset:[/green] {rp}")


if __name__ == "__main__":
    main()
