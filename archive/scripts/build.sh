#!/bin/bash
dir=$(dirname $(which $0));
cd $dir
#JSDIR="./media/xxxflash/js"
#cat $JSDIR/jquery-1.3.2.min.js \
#$JSDIR/jquery-ui-1.8.11.custom.min.js \
#$JSDIR/jquery.qtip-1.0.0-rc3.min.js \
#$JSDIR/main.js > $JSDIR/builded.js

CSSDIR="./media/xxxflash/css"
cat $CSSDIR/style.css > $CSSDIR/builded.css
python utils/slimcss.py $CSSDIR/builded.css



