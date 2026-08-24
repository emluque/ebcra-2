### Create Data dir

cd /home
mkdir data
mkdir data/postgres
mkdir data/mysql
sudo chown -R 999:root /home/data/postgres 
sudo chown -R 999:root /home/data/mysql 

cd /home
mkdir script-results

cd /home
mkdir nginx-logs
sudo chown -R www-data:www-data /home/nginx-logs