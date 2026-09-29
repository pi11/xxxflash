<?php

$xmlurl = 'http://gameboss.ru/x2.php?partner=55829&limit=1000&full=1&image=1';
//$xmlurl = 'gamelistgb.xml';

$gamesxml = file_get_contents($xmlurl);
$xml = new SimpleXMLElement($gamesxml);

$xml = $xml->result;

foreach ($xml->ITEM as $item){
    //print "ID: ".$item->ID."\n";
    
    
    
    print $item->RATE."|";
    print $item->NAME_URL."|";
    print $item->TYPE."|";
    print $item->ADDED."|";
    print $item->SIZE."|";
    print $item->NAME."|";
    print $item->MEDIUM_PIC."|";
    print $item->SMALL_PIC."|";
    print $item->DOWNLOAD_LINK."|";
    print $item->FULLDESCR."|";
    foreach ($item->SCREENSHOT as $s){
        print $s->IMAGE."|";
        print $s->THUMBNAIL."|";
    }
    print "#";
}

?>