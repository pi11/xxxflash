function esetCookie($Name,$Value,$EndH){ 
    var exdate=new Date(); 
    $EndH=exdate.getHours()+$EndH; 
    exdate.setHours($EndH); 
    document.cookie=$Name+ "=" +escape($Value)+(($EndH==null) ? "" : ";expires="+exdate.toGMTString()+"; path=/;");
}

function egetCookie($Name){ 
    if (document.cookie.length>0) { 
        $Start=document.cookie.indexOf($Name + "="); 
        if ($Start!=-1) { $Start=$Start + $Name.length+1; $End=document.cookie.indexOf(";",$Start); 
        if ($End==-1) $End=document.cookie.length; return unescape(document.cookie.substring($Start,$End)); 
        } 
    } 
    return "";
}

function should_show($ename){
    // должны ли мы показывать этот блок
    var cookie_name = $ename + "_xf";
    var shown = egetCookie(cookie_name);
    if (!shown){// еще не показывали
	esetCookie(cookie_name, 1, 24) // ставим куку на 24 часа
        return true;
    } else {
        return false;
    }
}