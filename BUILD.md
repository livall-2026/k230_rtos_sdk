# Build Instructions

## Requirements

---

### Compilation  Requirements

Ensure your system has all the necessary packages installed:

```bash
sudo apt-get install -y --no-install-recommends make autoconf automake bison flex gcc g++ \
gawk libncurses5-dev pkg-config libconfuse-dev libssl-dev python3 python3-pip python-is-python3 \
cmake libyaml-dev scons mtools bzip2 curl git openssh-client rsync dosfstools ca-certificates
```

Additionally, install Python packages using `pip`:

```bash
pip3 install pycryptodome gmssl scons==3.1.2
```

### Repository Requirements

To manage the source code, you need to install the `repo` tool:

1. Create a directory for the `repo` binary and add it to your `PATH`:

   ```bash
   mkdir -p ~/.bin
   export PATH="${HOME}/.bin:${PATH}"
   ```

2. Download the `repo` script and make it executable:

   ```bash
   curl https://storage.googleapis.com/git-repo-downloads/repo > ~/.bin/repo
   chmod a+rx ~/.bin/repo
   ```

3. Persist the `PATH` change by adding it to your shell configuration file (e.g., `~/.bashrc`):

   ```bash
   echo 'export PATH="${HOME}/.bin:${PATH}"' >> ~/.bashrc
   source ~/.bashrc
   ```

## Building the Project

---

### Get the Source Code

For the LIVALL development snapshot, initialize in a new directory:

```bash
repo init -u https://github.com/livall-2026/manifest -b livall-main -m default.xml \
  --repo-url=https://github.com/canmv-k230/git-repo.git --repo-branch stable
repo sync -c -j4
```

This branch follows the official development manifest. Its tracking branches
are resolved to a reproducible snapshot in `default.xml`; fixed third-party
dependencies remain at the revisions selected by upstream.

Local customizations retain the PMU shutdown handshake, GPIO startup guard,
`machine.PMU`, eMMC/1.8V, RTL8733BS on SDIO1 and CDC/MTP/ADB selection.
Storage drivers come from current upstream, with HS200 disabled by user choice.
The upstream composite USB implementation is used with the Windows MS OS
property-interface bounds fix retained. No dynamic preload-layout override is
applied. Always build with `env -u DEBUG make`.

Reports named `pre-sync`, `upstream-upgrade`, `repair` and `storage-fix` are
historical. Current validation is recorded in the LIVALL manifest repository.
A successful build does not imply hardware validation.

The following commands describe the original upstream checkout:

Initialize and sync the repository to get download the source code:

```bash
# from github with https
repo init -u https://github.com/canmv-k230/manifest -b master --repo-url=https://github.com/canmv-k230/git-repo.git

# or from gitee with ssh, need setup your ssh key
repo init -u git@gitee.com:canmv-k230/manifest.git -b master --repo-url=git@gitee.com:canmv-k230/git-repo.git

repo sync
```

### Build for a Specific Board

1. **Download the toolchain** (only required for the first build):

   ```bash
   make dl_toolchain
   ```

2. **Select a configuration** for your board:

   ```bash
   make list-def
   ```

   The terminal selector groups configurations by firmware type and chip. Use
   Left/Right to choose Arduino, CanMV, or RT-Smart, Tab to choose K230 or K230D,
   Up/Down to choose a board, and Enter to apply the selected defconfig. You can
   open a filtered selector with, for example,
   `make list-def TYPE=rtos CHIP=k230d`.

   In a non-interactive terminal, `make list-def` prints the grouped list without
   changing the current configuration. The selector supports Python 2.7 and
   Python 3; use `make list-def PYTHON=python2` when Python 2 is required.

3. **Alternatively, apply a configuration directly**:

   ```bash
   make k230_canmv_defconfig  # Replace with the appropriate defconfig for your board
   ```

4. **Start the build process**:

   ```bash
   time make log
   ```

This process will compile the software tailored to your selected board configuration.

## How to Contribute to This Project

---

This project is open-source and welcomes contributions.
For detailed information on how to contribute, please refer to the [CONTRIBUTING.md](CONTRIBUTING.md) file.

## Release build environment

Build with `env -u DEBUG make`. MicroPython treats any nonempty `DEBUG` value
(including `release` and `0`) as a debug build: it selects `-Og` and skips
stripping the final ELF. This is separate from RT-Smart `CONFIG_RT_DEBUG`.
When changing this environment, first run `env -u DEBUG make canmv-clean`
to rebuild cached CanMV objects and relink the ELF. The release image uses
the upstream fixed rtapp preload address; its stripped ELF must fit the
128 MiB board's 42.67 MiB preload window.
