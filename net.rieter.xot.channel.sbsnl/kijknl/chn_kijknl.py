import datetime

import mediaitem
import chn_class
from helpers.subtitlehelper import SubtitleHelper
from parserdata import ParserData

from streams.m3u8 import M3u8
from streams.mpd import Mpd
from regexer import Regexer
from helpers.jsonhelper import JsonHelper
from helpers.datehelper import DateHelper
from logger import Logger
from urihandler import UriHandler
from addonsettings import AddonSettings
# from helpers.languagehelper import LanguageHelper


class Channel(chn_class.Channel):
    """
    main class from which all channels inherit
    """

    def __init__(self, channelInfo):
        """Initialisation of the class.

        Arguments:
        channelInfo: ChannelInfo - The channel info object to base this channel on.

        All class variables should be instantiated here and this method should not
        be overridden by any derived classes.

        """

        chn_class.Channel.__init__(self, channelInfo)

        # ============== Actual channel setup STARTS here and should be overwritten from derived classes ===============
        # setup the urls
        self.baseUrl = "https://www.kijk.nl"
        # Just retrieve a single page with 500 items (should be all)

        use_html = False
        if use_html:
            self.mainListUri = "https://www.kijk.nl/programmas"
        else:
            self.mainListUri = "https://api.kijk.nl/v1/default/sections/programs-abc-0123456789abcdefghijklmnopqrstuvwxyz?limit=350&offset=0"

        self.__channelId = self.channelCode
        if self.channelCode == 'veronica':
            self.noImage = "veronicaimage.png"
            self.__channelId = "veronicatv"

        elif self.channelCode == 'sbs':
            self.noImage = "sbs6image.png"
            self.__channelId = "sbs6"

        elif self.channelCode == 'sbs9':
            self.noImage = "sbs9image.png"

        elif self.channelCode == 'net5':
            self.noImage = "net5image.png"

        else:
            self.noImage = "kijkimage.png"

        # setup the main parsing data
        self._AddDataParser("https://api.kijk.nl/v1/default/sections/programs-abc",
                            name="Mainlist Json", json=True,
                            preprocessor=self.AddOthers,
                            parser=("items", ), creator=self.CreateJsonEpisodeItem)

        self._AddDataParser("https://www.kijk.nl/programmas", matchType=ParserData.MatchExact,
                            name="Mainlist from HTML", json=True,
                            preprocessor=self.ExtractMainListJson)

        self._AddDataParser("https://api.kijk.nl/v2/templates/page/format/",
                            name="Videos from the main show format page", json=True,
                            parser=("components", 3, "data", "items", 2, "data", "items"),
                            creator=self.CreateJsonSeasonItem)

        self._AddDataParser("#lastweek",
                            name="Last week listing", json=True,
                            preprocessor=self.ListDates)

        self._AddDataParsers(("https://api.kijk.nl/v2/templates/page/missed/all/",
                              "https://api.kijk.nl/v1/default/sections/missed-all-"),
                             name="Day listing", json=True, preprocessor=self.ExtractDayItems)

        self._AddDataParser("https://api.kijk.nl/v1/default/searchresultsgrouped",
                            name="VideoItems Json", json=True,
                            parser=(), creator=self.CreateJsonSearchItem)

        self._AddDataParsers(("https://api.kijk.nl/v1/default/sections/series",
                              "https://api.kijk.nl/v1/default/seasons/"),
                             name="VideoItems Json", json=True,
                             parser=("items", ), creator=self.CreateJsonVideoItem)

        self._AddDataParser("https://api.kijk.nl/v2/default/sections/popular",
                            name="Popular items Json", json=True,
                            parser=("items", ), creator=self.CreateJsonPopularItem)

        self._AddDataParser("https://embed.kijk.nl/",
                            updater=self.UpdateJsonVideoItem)

        #===============================================================================================================
        # non standard items

        #===============================================================================================================
        # Test cases:
        #  Piets Weer: no clips
        #  Achter gesloten deuren: seizoenen
        #  Wegmisbruikers: episodes and clips and both pages
        #  Utopia: no clips
        #  Grand Designs has almost all encrypted/non-encrypted/brigthcove streams

        # ====================================== Actual channel setup STOPS here =======================================
        UriHandler.SetCookie(name="OPTOUTMULTI", value="0:0%7Cc5:0%7Cc1:0%7Cc4:0%7Cc3:0%7Cc2:0", domain=".kijk.nl")
        return

    def ExtractMainListJson(self, data):
        data, items = self.AddOthers(data)
        start_string = "window.__REDUX_STATE__ = "
        start_data = data.index(start_string)
        end_data = data.index("</script><script async=")
        data = data[start_data + len(start_string):end_data]
        data = JsonHelper(data)
        letters = data.get_value("reduxAsyncConnect", "page", "components", 1, "data", "items", 1, "data", "items")
        for letter_data in letters:
            letter_data = letter_data["data"]
            Logger.trace("Processing '%s'", letter_data["title"])
            for item in letter_data["items"]:
                episode = self.CreateJsonEpisodeItem(item)
                items.append(episode)
        return data, items

    def AddOthers(self, data):
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

        Logger.info("Performing Pre-Processing")
        items = []

        others = mediaitem.MediaItem("\b.: Populair :.", "https://api.kijk.nl/v2/default/sections/popular_PopularVODs?offset=0")
        items.append(others)

        days = mediaitem.MediaItem("\b.: Deze week :.", "#lastweek")
        items.append(days)

        search = mediaitem.MediaItem("\b.: Zoeken :.", "searchSite")
        search.complete = True
        search.icon = self.icon
        search.thumb = self.noImage
        search.dontGroup = True
        search.HttpHeaders = {"X-Requested-With": "XMLHttpRequest"}
        items.append(search)

        Logger.debug("Pre-Processing finished")
        return data, items

    # noinspection PyUnusedLocal
    def SearchSite(self, url=None):  # @UnusedVariable
        """Creates an list of items by searching the site

        Returns:
        A list of MediaItems that should be displayed.

        This method is called when the URL of an item is "searchSite". The channel
        calling this should implement the search functionality. This could also include
        showing of an input keyboard and following actions.

        """

        url = "https://api.kijk.nl/v1/default/searchresultsgrouped?search=%s"
        return chn_class.Channel.SearchSite(self, url)

    def ListDates(self, data):
        items = []

        # https://api.kijk.nl/v2/templates/page/missed/all/20180201
        days = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
        for i in range(0, 7):
            date = datetime.datetime.now() - datetime.timedelta(days=i)
            # https://api.kijk.nl/v2/templates/page/missed/all/20180626
            # url = "https://api.kijk.nl/v2/templates/page/missed/all/{0}{1:02d}{2:02d}".format(date.year, date.month, date.day)
            # https://api.kijk.nl/v1/default/sections/missed-all-20180619
            url = "https://api.kijk.nl/v1/default/sections/missed-all-{0}{1:02d}{2:02d}".format(date.year, date.month, date.day)
            if i == 0:
                # title = LanguageHelper.get_localized_string(LanguageHelper.Today)
                title = "Vandaag"
            elif i == 1:
                # title = LanguageHelper.get_localized_string(LanguageHelper.Yesterday)
                title = "Gisteren"
            elif i == 2:
                # title = LanguageHelper.get_localized_string(LanguageHelper.DayBeforeYesterday)
                title = "Eergisteren"
            else:
                day_name = days[date.weekday()]
                title = day_name

            date_item = mediaitem.MediaItem(title, url)
            date_item.set_date(date.year, date.month, date.day)
            items.append(date_item)

        Logger.debug("Pre-Processing finished")
        return data, items

    def ExtractDayItems(self, data):
        items = []
        json = JsonHelper(data)
        page_items = json.get_value('items')
        for item in page_items:
            video_item = self.CreateJsonVideoItem(item, prepend_serie=True)
            if video_item:
                items.append(video_item)
            else:
                pass

        return data, items

    def CreateJsonSearchItem(self, resultSet):
        if 'type' in resultSet:
            item_type = resultSet['type']
            if item_type == 'series':
                return self.CreateJsonEpisodeItem(resultSet)
            elif item_type == 'episode' or item_type == 'clip':
                return self.CreateJsonVideoItem(resultSet, prepend_serie=True)
        return None

    def CreateJsonSeasonItem(self, result_set):
        Logger.trace(result_set)
        # {
        #     "seasonNumber": 3,
        #     "id": "season-3",
        #     "episodesId": "achtergeslotendeuren.net5-season-3-episodes",
        #     "clipsId": "achtergeslotendeuren.net5-season-3-clips",
        #     "title": "Seizoen 3",
        #     "format": "achtergeslotendeuren",
        #     "channel": "net5",
        #     "episodesLink": "https://api.kijk.nl/v1/default/seasons/achtergeslotendeuren.net5/3/episodes",
        #     "clipsLink": "https://api.kijk.nl/v1/default/seasons/achtergeslotendeuren.net5/3/clips"
        # }
        # https://api.kijk.nl/v1/default/seasons/achtergeslotendeuren.net5/2/episodes?limit=100&offset=1

        url = "{episodesLink}?limit=100&offset=1".format(**result_set)
        item = mediaitem.MediaItem(result_set["title"], url)
        item.fanart = self.parentItem.fanart
        item.thumb = self.parentItem.thumb
        return item

    def CreateJsonEpisodeItem(self, resultSet):
        Logger.trace(resultSet)

        channelId = resultSet["channel"]
        if self.__channelId and channelId != self.__channelId:
            return None

        title = resultSet["title"]

        use_season = False
        if use_season:
            url = "https://api.kijk.nl/v2/templates/page/format/{id}".format(**resultSet)
        else:
            url = "https://api.kijk.nl/v1/default/sections/series-%(id)s_Episodes-season-0?limit=100&offset=0" % resultSet

        item = mediaitem.MediaItem(title, url)
        item.description = resultSet.get("synopsis", None)

        if "retina_image_pdp_header" in resultSet["images"]:
            item.fanart = resultSet["images"]["retina_image_pdp_header"]
        if "retina_image" in resultSet["images"]:
            item.thumb = resultSet["images"]["retina_image"]
        elif "nonretina_image" in resultSet["images"]:
            item.thumb = resultSet["images"]["nonretina_image"]

        return item

    def CreateJsonPopularItem(self, resultSet):
        item = self.CreateJsonVideoItem(resultSet, prepend_serie=True)
        if item is None:
            return None

        item.name = "%s - %s" % (item.name, resultSet["seriesTitle"])
        return item

    def CreateJsonVideoItem(self, resultSet, prepend_serie=False):
        Logger.trace(resultSet)

        if not resultSet.get("available", True):
            Logger.warning("Item not available: %s", resultSet)
            return None

        item = self.CreateJsonEpisodeItem(resultSet)
        if item is None:
            return None

        if prepend_serie and 'seriesTitle' in resultSet:
            item.name = "{0} - {1}".format(item.name, resultSet['seriesTitle'])
        elif 'seriesTitle' in resultSet:
            item.name = resultSet['seriesTitle']

        item.type = "video"
        item.url = "https://embed.kijk.nl/api/video/%(id)s?id=kijkapp&format=DASH&drm=CENC" % resultSet

        if 'subtitle' in resultSet:
            item.name = "{0} - {1}".format(item.name, resultSet['subtitle'])

        if "date" in resultSet:
            date = resultSet["date"].split("+")[0]
            # 2016-12-25T17:58:00+01:00
            timeStamp = DateHelper.get_date_from_string(date, "%Y-%m-%dT%H:%M:%S")
            item.set_date(*timeStamp[0:6])

        return item

    def UpdateJsonVideoItem(self, item):
        data = UriHandler.Open(item.url, proxy=self.proxy,
                               additionalHeaders={
                                   "accept": "application/vnd.sbs.ovp+json; version=2.0"
                               })
        json = JsonHelper(data)

        useAdaptiveWithEncryption = AddonSettings.use_adaptive_stream_add_on(with_encryption=True)
        # useAdaptiveWithEncryption = False
        mpdInfo = json.get_value("entitlements", "play")
        part = item.create_new_empty_media_part()

        # is there MPD information in the API response?
        if mpdInfo is not None:
            mpdManifestUrl = "https:{0}".format(mpdInfo["mediaLocator"])
            mpdData = UriHandler.Open(mpdManifestUrl, proxy=self.proxy)
            subtitles = Regexer.do_regex('<BaseURL>([^<]+\.vtt)</BaseURL>', mpdData)
            if subtitles:
                Logger.debug("Found subtitle: %s", subtitles[0])
                subtitle = SubtitleHelper.download_subtitle(subtitles[0],
                                                            proxy=self.proxy,
                                                            format="webvtt")
                part.Subtitle = subtitle

            if useAdaptiveWithEncryption:
                # We can use the adaptive add-on with encryption
                Logger.info("Using MPD InputStreamAddon")
                licenseUrl = Regexer.do_regex('licenseUrl="([^"]+)"', mpdData)[0]
                token = "Bearer {0}".format(mpdInfo["playToken"])
                keyHeaders = {"Authorization": token}
                licenseKey = Mpd.get_license_key(licenseUrl, key_headers=keyHeaders)

                stream = part.append_media_stream(mpdManifestUrl, 0)
                Mpd.set_input_stream_addon_input(stream, self.proxy, license_key=licenseKey)
                item.complete = True
                return item

        # Try the plain M3u8 streams
        m3u8Url = json.get_value("playlist")
        useAdaptive = AddonSettings.use_adaptive_stream_add_on()
        # with the Accept: application/vnd.sbs.ovp+json; version=2.0 header, the m3u8 streams that
        # are brightcove based have an url paramter instead of an empty m3u8 file
        Logger.debug("Trying standard M3u8 streams.")
        if m3u8Url != "https://embed.kijk.nl/api/playlist/.m3u8" \
                and "hostingervice=brightcove" not in m3u8Url:
            for s, b in M3u8.get_streams_from_m3u8(m3u8Url, self.proxy, append_query_string=True):
                if "_enc_" in s:
                    continue

                if useAdaptive:
                    # we have at least 1 none encrypted streams
                    Logger.info("Using HLS InputStreamAddon")
                    strm = part.append_media_stream(m3u8Url, 0)
                    M3u8.set_input_stream_addon_input(strm, proxy=self.proxy)
                    item.complete = True
                    return item

                part.append_media_stream(s, b)
                item.complete = True
            return item

        Logger.warning("No M3u8 data found. Falling back to BrightCove")
        videoId = json.get_value("vpakey")
        # videoId = json.get_value("videoId") -> Not all items have a videoId
        mpdManifestUrl = "https://embed.kijk.nl/video/%s?width=868&height=491" % (videoId,)
        referer = "https://embed.kijk.nl/video/%s" % (videoId,)

        data = UriHandler.Open(mpdManifestUrl, proxy=self.proxy, referer=referer)
        # First try to find an M3u8
        m3u8Urls = Regexer.do_regex('https:[^"]+.m3u8', data)
        for m3u8Url in m3u8Urls:
            m3u8Url = m3u8Url.replace("\\", "")
            Logger.debug("Found direct M3u8 in brightcove data.")
            if useAdaptive:
                # we have at least 1 none encrypted streams
                Logger.info("Using HLS InputStreamAddon")
                strm = part.append_media_stream(m3u8Url, 0)
                M3u8.set_input_stream_addon_input(strm, proxy=self.proxy)
                item.complete = True
                return item

            for s, b in M3u8.get_streams_from_m3u8(m3u8Url, self.proxy, append_query_string=True):
                item.complete = True
                part.append_media_stream(s, b)

            return item

        # Then try the new BrightCove JSON
        brightCoveRegex = '<video[^>]+data-video-id="(?<videoId>[^"]+)[^>]+data-account="(?<videoAccount>[^"]+)'
        brightCoveData = Regexer.do_regex(Regexer.from_expresso(brightCoveRegex), data)
        if brightCoveData:
            Logger.info("Found new BrightCove JSON data")
            brightCoveUrl = 'https://edge.api.brightcove.com/playback/v1/accounts/%(videoAccount)s/videos/%(videoId)s' % \
                            brightCoveData[0]
            headers = {
                "Accept": "application/json;pk=BCpkADawqM3ve1c3k3HcmzaxBvD8lXCl89K7XEHiKutxZArg2c5RhwJHJANOwPwS_4o7UsC4RhIzXG8Y69mrwKCPlRkIxNgPQVY9qG78SJ1TJop4JoDDcgdsNrg"}
            brightCoveData = UriHandler.Open(brightCoveUrl, proxy=self.proxy,
                                             additionalHeaders=headers)
            brightCoveJson = JsonHelper(brightCoveData)
            streams = filter(lambda d: d["container"] == "M2TS", brightCoveJson.get_value("sources"))
            if streams:
                # noinspection PyTypeChecker
                streamUrl = streams[0]["src"]

                # these streams work better with the the InputStreamAddon because it removes the
                # "range" http header
                if useAdaptiveWithEncryption:
                    Logger.info("Using InputStreamAddon for playback of HLS stream")
                    strm = part.append_media_stream(streamUrl, 0)
                    strm.add_property("inputstreamaddon", "inputstream.adaptive")
                    strm.add_property("inputstream.adaptive.manifest_type", "hls")
                    item.complete = True
                    return item

                for s, b in M3u8.get_streams_from_m3u8(streamUrl, self.proxy):
                    item.complete = True
                    part.append_media_stream(s, b)
                return item
