ALTER TABLE "flash_flash" ADD   "datahash" varchar(512);
ALTER TABLE "flash_flash" ADD    "is_posted" boolean NOT NULL default false;
ALTER TABLE "flash_flash" drop old_description;
ALTER TABLE "flash_flash" ALTER "datahash" SET NOT NULL;
ALTER TABLE "flash_flash" ADD CONSTRAINT uk_datahash UNIQUE (datahash);