import os
import tempfile
from barman.cloud import CloudBackup
from barman.command_wrappers import Command


class KopiaCloudInterface(object):
    def __init__(self, *args, **kwargs):
        pass

    def test_connectivity(self):
        return True

    def close(self):
        pass

    def setup_bucket(self):
        pass


class CloudBackupKopia(CloudBackup):
    def __init__(
        self,
        server_name,
        cloud_interface,
        max_archive_size,
        postgres,
        compression=None,
        backup_name=None,
        **kwargs,
    ):
        super(CloudBackupKopia, self).__init__(
            server_name,
            cloud_interface,
            postgres,
            backup_name=backup_name,
        )

    def _take_backup(self):
        """
        Take a kopia snapshot including PGDATA and all tablespaces.
        """
        tablespaces = []
        for tablespace in self.backup_info.tablespaces:
            if tablespace.location.startswith(self.backup_info.pgdata + "/"):
                # We can't exclude the tablespace from the copy if they're in PGDATA
                # but we can avoid adding it to the snapshot a second time.
                continue
            # The symlinks in pg_tblspc will be copied as symlinks so we don't
            # need to exclude them.
            tablespaces.append(tablespace.location)

        kopia_cmd = Kopia(
            "kopia",
            "snapshot",
            [
                "create",
                self.backup_info.pgdata,
                *(self._tags_args + ["--tags", "type:pgdata"]),
            ],
        )
        kopia_cmd()

        kopia_cmd = Kopia(
            "kopia",
            "snapshot",
            [
                "create",
                *tablespaces,
                *(self._tags_args + ["--tags", "type:tablespace"]),
            ],
        )
        kopia_cmd()

    def _upload_backup_label(self):
        """No-op because backup label gets added to a snapshot with backup.info."""
        pass

    def _add_stats_to_backup_info(self):
        """Maybe add some useful stuff here?"""
        pass

    def _finalise_copy(self):
        """Probably nothing to do here."""
        pass

    def _upload_backup_info(self):
        """Create a separate kopia snapshot with just the metadata."""
        # Write both the backup label and backup info to a staging location
        tempdir = tempfile.mkdtemp(prefix="backup-metadata")
        if self.backup_info.backup_label is not None:
            with open(os.path.join(tempdir, "backup_label"), "w") as backup_label:
                backup_label.write(self.backup_info.backup_label)
        self.backup_info.save(filename=os.path.join(tempdir, "backup.info"))
        # Create a kopia snapshot of that location and tag accordingly
        kopia_cmd = Kopia(
            "kopia",
            "snapshot",
            [
                "create",
                tempdir,
                *(self._tags_args + ["--tags", "type:metadata"]),
            ],
        )
        kopia_cmd()

    def backup(self):
        """
        Upload a Backup via Kopia, probably
        """
        server_name = "cloud"
        self.backup_info = self._get_backup_info(server_name)

        self._check_postgres_version()

        # Figure out the tags for use later in the process
        self._tags_args = ["--tags", f"backup_id:{self.backup_info.backup_id}"]
        if self.backup_name is not None:
            self._tags_args.extend(["--tags", f"backup_name:{self.backup_name}"])

        self._coordinate_backup()


class Kopia(Command):
    """
    Wrapper for the kopia command.
    """

    def __init__(
        self,
        kopia="kopia",
        subcommand=None,
        args=None,
        path=None,
    ):
        options = []
        if subcommand is not None:
            options += [subcommand]
        if args is not None:
            options += args
        super(Kopia, self).__init__(kopia, args=options, path=path)
