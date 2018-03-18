import logging
import os
logger = logging.getLogger(__package__)



class Sync():
    """
    Sync files from server using rsync.
    Optimized download and upload only of necessary files.
    """
    def __init__(self, site, optimized_mark):
        self.site = site
        self.remote_cache_path = '{}wp-content/cache/'.format(site.wp_path)
        self.optimized_mark = optimized_mark
        self._prepare_work_dir()


    def _prepare_work_dir(self):
        """
        Define the directory to save files, clean if exists and recreate it.
        :return:
        """
        self.work_dir = '/tmp/cache_optimizer/{}/'.format(self.site.label)
        os.system('rm -rf {}'.format(self.work_dir))
        os.system('mkdir -p {}'.format(self.work_dir))


    def _list_remote_files_to_optimize(self):
        """
        Check remote files that are not optimized yet (does not have the optimized_mark).
        :return: full remote path of every file to be downloaded and optimized.
        """
        c_optimized_files = 'grep -H -R "{}" {} | cut -d: -f1'.format(
            # re.escape did not work here...
            self.optimized_mark.replace('!','\!').replace('-','\-'),
            self.remote_cache_path
        )

        optimized_files = self.site.ssh_command(c_optimized_files)
        # all_files = self.site.ssh_command('ls -f {}'.format(self.remote_cache_path))
        all_files = self.site.ssh_command('find {} -maxdepth 1 -type f -printf "%p\n"'.format(
            self.remote_cache_path
        ))

        optimized_files = [f.strip() for f in optimized_files if 'qc-c-' in f]
        all_files = [f.strip() for f in all_files if 'qc-c-' in f]

        return [f.strip() for f in all_files if f not in optimized_files]


    def download(self):
        """
        Download files using rsync, but only the necessary files
        :return: list of files to be optimized."""
        files_to_download = self._list_remote_files_to_optimize()
        files_to_download = [os.path.basename(f) for f in files_to_download]

        logger.info('{} files to optimize!'.format(len(files_to_download)))

        file_to_save_list = '{}files_to_download.txt'.format(self.work_dir)
        open(file_to_save_list,'w').write('\n'.join(
            ['{}'.format(f) for f in files_to_download]
        ))

        c_rsync = 'rsync -cazv --files-from={}'.format(file_to_save_list)
        c_rsync += ' {}@{}:{}'.format(self.site.ssh_user, self.site.domain, self.remote_cache_path)
        c_rsync += ' {}'.format(self.work_dir)

        os.system(c_rsync)
        os.system('rm {}'.format(file_to_save_list))

        return ['{}{}'.format(self.work_dir, f) for f in files_to_download]


    def up(self, directory):
        c_rsync = 'rsync -cazv '
        # c_rsync = '--dry-run '
        c_rsync += ' {}'.format(directory)
        c_rsync += ' {}@{}:{}'.format(self.site.ssh_user, self.site.domain, self.remote_cache_path)
        os.system(c_rsync)


