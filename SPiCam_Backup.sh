now=$(date +'%Y%m%d%H%M%S')
file_name="SPiCam_Backup_$now.tar.gz"
tar -vzcf $file_name /home/pi/SPiCam/images/
rm -rf /home/pi/SPiCam/images/*
mv $file_name "/backups/$file_name"
