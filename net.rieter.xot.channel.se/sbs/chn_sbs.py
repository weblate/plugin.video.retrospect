# coding:UTF-8

import uuid

import mediaitem
import chn_class

from helpers.jsonhelper import JsonHelper
from helpers.subtitlehelper import SubtitleHelper
from urihandler import UriHandler
from streams.m3u8 import M3u8
from helpers.htmlentityhelper import HtmlEntityHelper
from parserdata import ParserData
from logger import Logger
from xbmcwrapper import XbmcWrapper


# noinspection PyIncorrectDocstring
class Channel(chn_class.Channel):

    def __init__(self, channelInfo):
        """Initialisation of the class.

        Arguments:
        channelInfo: ChannelInfo - The channel info object to base this channel on.

        All class variables should be instantiated here and this method should not
        be overridden by any derived classes.

        """

        chn_class.Channel.__init__(self, channelInfo)

        # ==== Actual channel setup STARTS here and should be overwritten from derived classes =====
        self.mainListUri = "#programs"
        self.programPageSize = 100
        self.videoPageSize = 25
        self.swfUrl = "http://player.dplay.se/4.0.6/swf/AkamaiAdvancedFlowplayerProvider_v3.8.swf"
        self.subtitleKey = "subtitles_se_srt"
        self.channelSlugs = ()
        self.liveUrl = None
        self.recentUrl = None

        if self.channelCode == "tv5json":
            self.noImage = "tv5seimage.png"
            self.baseUrl = "http://www.dplay.se/api/v2/ajax"
            # self.liveUrl = "https://secure.dplay.se/secure/api/v2/user/authorization/stream/132040"
            # self.fanart = "http://a1.res.cloudinary.com/dumrsasw1/image/upload/Kanal5-channel-large_kxf7fn.jpg"
            # Recent URL changes over time. See the 'website -> channel' page
            self.recentUrl = "%s/modules?page_id=132040&module_id=7556&items=%s&page=0"
            self.primaryChannelId = 21

        elif self.channelCode == "tv9json":
            self.noImage = "tv9seimage.png"
            self.baseUrl = "http://www.dplay.se/api/v2/ajax"
            # self.liveUrl = "https://secure.dplay.se/secure/api/v2/user/authorization/stream/132043"
            # self.fanart = "http://a2.res.cloudinary.com/dumrsasw1/image/upload/Thewalkingdead_hqwfz1.jpg"
            self.recentUrl = "%s/modules?page_id=132043&module_id=466&items=%s&page=0"
            self.primaryChannelId = 26

        elif self.channelCode == "tv11json":
            self.noImage = "tv11seimage.jpg"
            self.baseUrl = "http://www.dplay.se/api/v2/ajax"
            # self.liveUrl = "https://secure.dplay.se/secure/api/v2/user/authorization/stream/132039"
            # self.fanart = "http://a3.res.cloudinary.com/dumrsasw1/image/upload/unnamed_v3u5zt.jpg"
            self.recentUrl = "%s/modules?page_id=132039&module_id=470&items=%s&page=0"
            self.primaryChannelId = 22

        else:
            raise NotImplementedError("ChannelCode %s is not implemented" % (self.channelCode, ))

        #===========================================================================================
        # THIS CHANNEL DOES NOT SEEM TO WORK WITH PROXIES VERY WELL!
        #===========================================================================================
        self._AddDataParser("#programs", preprocessor=self.LoadPrograms)
        self._AddDataParser("https://secure.dplay.\w+/secure/api/v2/user/authorization/stream/",
                            matchType=ParserData.MatchRegex,
                            updater=self.UpdateChannelItem)

        # TODO: Search
        self._AddDataParser("http://www.dplay.se/api/v2/ajax/search/?types=show&items=", json=True,
                            parser=("data", ), creator=self.CreateProgramItem)

        self._AddDataParser("http://www.dplay.se/api/v2/ajax/modules", json=True,
                            parser=("data",), creator=self.CreateVideoItemWithShowTitle,
                            updater=self.UpdateVideoItem)

        self._AddDataParser("*", json=True,
                            preprocessor=self.__GetImagesFromMetaData,
                            parser=("data",), creator=self.CreateVideoItem,

                            updater=self.UpdateVideoItem)
        # TODO: Video paging
        self._AddDataParser("*", json=True,
                            parser=(), creator=self.CreatePageItem)

        #===========================================================================================
        # non standard items
        if not UriHandler.GetCookie("st", "disco-api.dplay.se"):
            guid = uuid.uuid4()
            guid = str(guid).replace("-", "")
            # https://disco-api.dplay.se/token?realm=dplayse&deviceId
            # =aa9ef0ed760df76d184b262d739299a75ccae7b67eec923fe3fcd861f97bcc7f&shortlived=true
            url = "https://disco-api.dplay.se/token?realm=dplayse&deviceId={0}&shortlived=true".format(guid)
            JsonHelper(UriHandler.Open(url, proxy=self.proxy))

        self.imageLookup = {}

        #===========================================================================================
        # Test cases:
        #  Arga snickaren : Has clips

        # ====================================== Actual channel setup STOPS here ===================
        return

    # noinspection PyUnusedLocal
    def LoadPrograms(self, data):
        """Performs pre-process actions for data processing/

        Arguments:
        data : string - the retrieve data that was loaded for the current item and URL.

        Returns:
        A tuple of the data and a list of MediaItems that were generated.


        Accepts an data from the ProcessFolderList method, BEFORE the items are
        processed. Allows setting of parameters (like title etc) for the channel.
        Inside this method the <data> could be changed and additional items can
        be created.

        The return values should always be instantiated in at least ("", []).
        """

        items = []

        # fetch al pages
        p = 1
        urlFormat = "https://disco-api.dplay.se/content/shows?" \
                    "include=images" \
                    "&page%5Bsize%5D=100&page%5Bnumber%5D={0}"
        # "include=images%2CprimaryChannel" \
        url = urlFormat.format(p)
        data = UriHandler.Open(url, proxy=self.proxy)
        json = JsonHelper(data)
        pages = json.GetValue("meta", "totalPages")
        programs = json.GetValue("data") or []

        # extract the images
        self.__UpdateImageLookup(json)

        # https://disco-api.dplay.se/content/shows?include=genres%2Cimages%2CprimaryChannel.images
        # &page%5Bsize%5D=100&page%5Bnumber%5D=1
        # https://disco-api.dplay.se/content/shows?page%5Bsize%5D=100&page%5Bnumber%5D=1

        for p in range(2, pages + 1, 1):
            url = urlFormat.format(p)
            Logger.Debug("Loading: %s", url)

            data = UriHandler.Open(url, proxy=self.proxy)
            json = JsonHelper(data)
            programs += json.GetValue("data") or []

            # extract the images
            self.__UpdateImageLookup(json)

        Logger.Debug("Found a total of %s items over %s pages", len(programs), pages)

        for p in programs:
            item = self.CreateProgramItem(p)
            if item is not None:
                items.append(item)

        if self.recentUrl:
            url = self.recentUrl % (self.baseUrl, self.videoPageSize)
            recent = mediaitem.MediaItem("\b.: Recent :.", url)
            recent.dontGroup = True
            recent.fanart = self.fanart
            items.append(recent)

        # live items
        if self.liveUrl:
            live = mediaitem.MediaItem("\b.: Live :.", self.liveUrl)
            live.type = "video"
            live.dontGroup = True
            live.isGeoLocked = True
            live.isLive = True
            live.fanart = self.fanart
            items.append(live)

        search = mediaitem.MediaItem("\a.: S&ouml;k :.", "searchSite")
        search.type = "folder"
        search.dontGroup = True
        search.fanart = self.fanart
        items.append(search)

        return data, items

    def CreateProgramItem(self, resultSet):
        """Creates a new MediaItem for a program

        Arguments:
        resultSet : list[string] - the resultSet of the self.episodeItemRegex

        Returns:
        A new MediaItem of type 'folder'

        This method creates a new MediaItem from the Regular Expression or Json
        results <resultSet>. The method should be implemented by derived classes
        and are specific to the channel.

        """

        Logger.Trace(resultSet)
        urlFormat = "https://disco-api.dplay.se/content/videos?decorators=viewingHistory&" \
                    "include=images%2CprimaryChannel%2Cshow&" \
                    "filter%5BvideoType%5D=EPISODE%2CLIVE&" \
                    "filter%5Bshow.id%5D={0}&" \
                    "page%5Bsize%5D=100&" \
                    "sort=-seasonNumber%2C-episodeNumber%2CearliestPlayableStart"
        item = self.__CreateGenericItem(resultSet, "show", urlFormat)
        if item is None:
            return None

        # set the date
        videoInfo = resultSet["attributes"]
        if "newestEpisodePublishStart" in videoInfo:
            date = videoInfo["newestEpisodePublishStart"]
            datePart, timePart = date[0:-3].split("T")
            year, month, day = datePart.split("-")
            item.SetDate(year, month, day)

        return item

    def CreatePageItem(self, resultSet):
        """Creates a MediaItem of type 'page' using the resultSet from the regex.

        Arguments:
        resultSet : tuple(string) - the resultSet of the self.pageNavigationRegex

        Returns:
        A new MediaItem of type 'page'

        This method creates a new MediaItem from the Regular Expression or Json
        results <resultSet>. The method should be implemented by derived classes
        and are specific to the channel.

        """
        return None

        Logger.Debug("Starting CreatePageItem")

        # # current page?
        # baseUrl, page = self.parentItem.url.rsplit("=", 1)
        # page = int(page)
        # maxPages = resultSet.get("total_pages", 0)
        # Logger.Trace("Current Page: %d of %d (%s)", page, maxPages, baseUrl)
        # if page + 1 >= maxPages:
        #     return None
        #
        # title = LanguageHelper.GetLocalizedString(LanguageHelper.MorePages)
        # url = "%s=%s" % (baseUrl, page + 1)
        # item = mediaitem.MediaItem(title, url)
        # item.fanart = self.parentItem.fanart
        # item.thumb = self.parentItem.thumb
        # return item

    def SearchSite(self, url=None):
        """Creates an list of items by searching the site

        Keyword Arguments:
        url : String - Url to use to search with a %s for the search parameters

        Returns:
        A list of MediaItems that should be displayed.

        This method is called when the URL of an item is "searchSite". The channel
        calling this should implement the search functionality. This could also include
        showing of an input keyboard and following actions.

        The %s the url will be replaced with an URL encoded representation of the
        text to search for.

        """

        # http://www.dplay.se/api/v2/ajax/search/?q=test&items=12&types=video&video_types=episode,live
        # http://www.dplay.se/api/v2/ajax/search/?q=test&items=6&types=show

        needle = XbmcWrapper.ShowKeyBoard()
        if needle:
            Logger.Debug("Searching for '%s'", needle)
            needle = HtmlEntityHelper.UrlEncode(needle)

            url = "http://www.dplay.se/api/v2/ajax/search/?types=video&items=%s" \
                  "&video_types=episode,live&q=%%s&page=0" % (self.videoPageSize, )
            searchUrl = url % (needle, )
            temp = mediaitem.MediaItem("Search", searchUrl)
            episodes = self.ProcessFolderList(temp)

            url = "http://www.dplay.se/api/v2/ajax/search/?types=show&items=%s" \
                  "&q=%%s&page=0" % (self.programPageSize, )
            searchUrl = url % (needle, )
            temp = mediaitem.MediaItem("Search", searchUrl)
            shows = self.ProcessFolderList(temp)
            return shows + episodes

        return []

    def CreateVideoItemWithShowTitle(self, resultSet):
        """Creates a MediaItem with ShowTitle """

        # Logger.Trace(resultSet)
        if not resultSet:
            return None

        title = resultSet["title"]
        showTitle = resultSet.get("video_metadata_show", None)
        if showTitle:
            resultSet["title"] = "%s - %s" % (showTitle, title)
        return self.CreateVideoItem(resultSet)

    def CreateVideoItem(self, resultSet):
        """Creates a MediaItem of type 'video' using the resultSet from the regex.

        Arguments:
        resultSet : tuple (string) - the resultSet of the self.videoItemRegex

        Returns:
        A new MediaItem of type 'video' or 'audio' (despite the method's name)

        This method creates a new MediaItem from the Regular Expression or Json
        results <resultSet>. The method should be implemented by derived classes
        and are specific to the channel.

        If the item is completely processed an no further data needs to be fetched
        the self.complete property should be set to True. If not set to True, the
        self.UpdateVideoItem method is called if the item is focussed or selected
        for playback.

        """

        # Logger.Trace(resultSet)
        if not resultSet:
            return None

        urlFormat = "https://disco-api.dplay.se/playback/videoPlaybackInfo/{0}"
        item = self.__CreateGenericItem(resultSet, "video", urlFormat)
        item.type = "video"
        if item is None:
            return None

        videoInfo = resultSet["attributes"]
        if "publishStart" in videoInfo:
            date = videoInfo["publishStart"]
            datePart, timePart = date[0:-3].split("T")
            year, month, day = datePart.split("-")
            item.SetDate(year, month, day)

        episode = videoInfo.get("episodeNumber", 0)
        season = videoInfo.get("seasonNumber", 0)
        if episode > 0 and season > 0:
            item.name = "s{0:02d}e{1:02d} - {2}".format(season, episode, item.name)
            item.SetSeasonInfo(season, episode)
        return item

    def UpdateChannelItem(self, item):
        """Updates an existing MediaItem with more data.

        Arguments:
        item : MediaItem - the MediaItem that needs to be updated

        Returns:
        The original item with more data added to it's properties.

        Used to update none complete MediaItems (self.complete = False). This
        could include opening the item's URL to fetch more data and then process that
        data or retrieve it's real media-URL.

        The method should at least:
        * cache the thumbnail to disk (use self.noImage if no thumb is available).
        * set at least one MediaItemPart with a single MediaStream.
        * set self.complete = True.

        if the returned item does not have a MediaItemPart then the self.complete flag
        will automatically be set back to False.

        """

        videoId = item.url.rsplit("/", 1)[-1]
        part = item.CreateNewEmptyMediaPart()
        item.complete = self.__GetVideoStreams(videoId, part)
        return item

    def UpdateVideoItem(self, item):
        """Updates an existing MediaItem with more data.

        Arguments:
        item : MediaItem - the MediaItem that needs to be updated

        Returns:
        The original item with more data added to it's properties.

        Used to update none complete MediaItems (self.complete = False). This
        could include opening the item's URL to fetch more data and then process that
        data or retrieve it's real media-URL.

        The method should at least:
        * cache the thumbnail to disk (use self.noImage if no thumb is available).
        * set at least one MediaItemPart with a single MediaStream.
        * set self.complete = True.

        if the returned item does not have a MediaItemPart then the self.complete flag
        will automatically be set back to False.

        """

        videoData = UriHandler.Open(item.url, proxy=self.proxy)

        if not videoData:
            return item

        videoData = JsonHelper(videoData)
        videoInfo = videoData.GetValue("data", "attributes")

        part = item.CreateNewEmptyMediaPart()
        m3u8url = videoInfo["streaming"]["hls"]["url"]
        m3u8data = UriHandler.Open(m3u8url, self.proxy)

        for s, b, a in M3u8.GetStreamsFromM3u8(m3u8url, self.proxy, appendQueryString=True,
                                               mapAudio=True, playListData=m3u8data):
            item.complete = True
            if a:
                audioPart = a.split("-prog_index.m3u8", 1)[0]
                audioId = audioPart.rsplit("/", 1)[-1]
                s = s.replace("-prog_index.m3u8", "-{0}-prog_index.m3u8".format(audioId))
            part.AppendMediaStream(s, b)

        vttUrl = M3u8.GetSubtitle(m3u8url, self.proxy, m3u8data)
        # https://dplaynordics-vod-80.akamaized.net/dplaydni/259/0/hls/243241001/1112635959-prog_index.m3u8?version_hash=bb753129&hdnts=st=1518218118~exp=1518304518~acl=/*~hmac=bdeefe0ec880f8614e14af4d4a5ca4d3260bf2eaa8559e1eb8ba788645f2087a
        vttUrl = vttUrl.replace("-prog_index.m3u8", "-0.vtt")
        part.Subtitle = SubtitleHelper.DownloadSubtitle(vttUrl, format='srt', proxy=self.proxy)
        return item

    def __GetImagesFromMetaData(self, data):
        items = []
        data = JsonHelper(data)
        self.__UpdateImageLookup(data)
        return data, items

    def __UpdateImageLookup(self, jsonData):
        images = filter(lambda a: a["type"] == "image", jsonData.GetValue("included"))
        images = {str(image["id"]): image["attributes"]["src"] for image in images}
        self.imageLookup.update(images)

    def __GetVideoStreams(self, videoId, part):
        """ Fetches the video stream for a given videoId

        @param videoId: (integer) the videoId
        @param part:    (MediaPart) the mediapart to add the streams to
        @return:        (bool) indicating a successfull retrieval

        """

        # hardcoded for now as it does not seem top matter
        dscgeo = '{"countryCode":"%s","expiry":1446917369986}' % (self.language.upper(),)
        dscgeo = HtmlEntityHelper.UrlEncode(dscgeo)
        headers = {"Cookie": "dsc-geo=%s" % (dscgeo, )}

        # send the data
        http, nothing, host, other = self.baseUrl.split("/", 3)
        subdomain, domain = host.split(".", 1)
        url = "https://secure.%s/secure/api/v2/user/authorization/stream/%s?stream_type=hls" \
              % (domain, videoId,)
        data = UriHandler.Open(url, proxy=self.proxy, additionalHeaders=headers, noCache=True)
        json = JsonHelper(data)
        url = json.GetValue("hls")

        if url is None:
            return False

        streamsFound = False
        if "?" in url:
            qs = url.split("?")[-1]
        else:
            qs = None
        for s, b in M3u8.GetStreamsFromM3u8(url, self.proxy):
            # and we need to append the original QueryString
            if "X-I-FRAME-STREAM" in s:
                continue

            streamsFound = True
            if qs is not None:
                if "?" in s:
                    s = "%s&%s" % (s, qs)
                else:
                    s = "%s?%s" % (s, qs)

            part.AppendMediaStream(s, b)

        return streamsFound

    def __CreateGenericItem(self, resultSet, expectedItemType, urlFormat):
        videoInfo = resultSet["attributes"]
        name = videoInfo["name"]

        if expectedItemType != resultSet["type"]:
            Logger.Warning("Not %s, excluding %s", expectedItemType, name)
            return None

        channelId = int(resultSet["relationships"]["primaryChannel"]["data"]["id"])
        if channelId != self.primaryChannelId:
            return None

        itemId = resultSet["id"]
        # showSlug = videoInfo["alternateId"]

        url = urlFormat.format(itemId)
        item = mediaitem.MediaItem(name, url)
        item.description = videoInfo.get("description")

        geoInfo = videoInfo.get("geoRestrictions", {"countries": ["world"]})
        item.isGeoLocked = "world" not in geoInfo.get("countries")

        # set the images
        thumbId = resultSet["relationships"]["images"]["data"][0]["id"]
        item.thumb = self.imageLookup.get(thumbId, self.noImage)
        if item.thumb == self.noImage:
            Logger.Warning("No thumb found for %s", thumbId)

        # paid or not?
        if "contentPackages" in resultSet["relationships"]:
            item.isPaid = len(
                filter(
                    lambda p: p["id"].lower() == "free", resultSet["relationships"]["contentPackages"]["data"]
                )
            ) <= 0
        else:
            item.isPaid = False

        return item
