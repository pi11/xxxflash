from django.conf.urls import include, url

from flash.views import *

urlpatterns = [

    url(r'^get_comments/(?P<game_id>\d+)/(?P<page_id>\d+)/$',
        get_comments, name='get_comments'),
    url(r'^game/(?P<game_id>\d+)/', game, name='view_game'),
    url(r'^upload/$', upload, name="upload_game"),
    url(r'^ban/(?P<comment_id>\d+)/$', ban, name="ban"),
    url(r'^mark/$', mark, name="mark"),

                       
    url(r'^$', index, name="index_page"),
    url(r'^best/$', best_games, name="best"),
    url(r'^best2/$', best_games2, name="best2"),
    url(r'^popular/$', popular_games, name="popular"),
    url(r'^random/$', random_games, name="random"),
    url(r'^theme/(?P<theme_url>[\-\w ]+)/$', theme, name='theme'),
    url(r'^add-comment', add_comment, name="add_comment"),
    url(r'^del-comment/(?P<comment_id>\d+)$', del_comment, name="del_comment"),

    url('^search/$', search, name='search'),
    url('^get-user-panel/$', get_user_panel, name='get_user_panel'),
    url('^search/(?P<query>.*?)$', search, name='search'),
                       
    url(r'^page/(\d+)/$', index_old, name="index_page_old"),
    url(r'^theme/(?P<theme_name>[\-\w ]+)/(?P<page_id>\d+)/$',
        theme_old, name="theme_old"),
    url(r'^best/page/(?P<page_id>\d+)/$',
        best_old, name="best_page_old"),
    url(r'^best2/page/(?P<page_id>\d+)/$',
        best2_old, name="best2_page_old"),
    url(r'^popular/page/(?P<page_id>\d+)/$',
        popular_old, name="popular_page_old"),

    url(r'^login/', login_view, name='login'),
    url(r'^logout/', logout_view, name='logout'),
    url(r'^auth/(?P<user_id>\d+)/(?P<token>\w+)/', auth, name='auth'),
    ]
