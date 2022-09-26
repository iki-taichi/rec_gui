//!/usr/local/miniwob-plusplus

var body_scale = 2.0;
document.body.style.overflow = "hidden";

Math.seedrandom("{{task_seed}}");
core.EPISODE_MAX_TIME = 1000*{{total_time_limit}};
document.getElementById("click-canvas").style.display='none'
document.getElementById("reward-display").style.display='none'

function request_get(url) {
    var xmlHttp = new XMLHttpRequest();
    xmlHttp.open("GET", url, false);
    xmlHttp.send(null);
    return xmlHttp.responseText;
}

var _startEpisodeReal = core.startEpisodeReal;
core.startEpisodeReal = function() {
    request_get("{{url_prefix}}/task/start_episode");
    _startEpisodeReal();
}

var _endEpisode = core.endEpisode;
core.endEpisode = function(reward, time_proportional, reason) {
    _endEpisode(reward, undefined, reason);
    request_get("{{url_prefix}}/task/end_episode?reward="+reward+"&reason="+reason);
}

var set_scale = function (s) {
  // set scale with css
  var b = document.body;
  b.style.transformOrigin = "0 0";
  b.style.transform = "scale("+s+")";
  
  // hack jQuery to scale pointer's position
  if (typeof jQuery !== 'undefined') {
    jQuery.event.addProp('pageY', (ev)=>(ev.pageY/s));
    jQuery.event.addProp('pageX', (ev)=>(ev.pageX/s));
    if (!jQuery.fn.hasOwnProperty('_offset')){
      jQuery.fn._offset = jQuery.fn.offset
    }
    jQuery.fn.offset = function () {
      if (arguments.length) {
        return jQuery.fn._offset.appyly(this, arguments);
      }
      
      var x = jQuery.fn._offset.call(this);
      return {
        left: x.left / s,
        top: x.top / s
      }
    }
  }

  // hack graphClicked
  if (typeof graphClicked !== 'undefined') {
    var _graphClicked = graphClicked
    graphClicked = function (event) {
      var event_wrapper = {}
      for (const property in event) {
        event_wrapper[ property ] = event[ property ];
      }
      event_wrapper['pageX'] /= s;
      event_wrapper['pageY'] /= s;
      _graphClicked(event_wrapper);
    }
  }
}
set_scale(body_scale);


//!http://nlpb-gui
function request_get(url) {
    var xmlHttp = new XMLHttpRequest();
    xmlHttp.open("GET", url, false);
    xmlHttp.send(null);
    return xmlHttp.responseText;
}

start_episode = function(){
    request_get("{{url_prefix}}/task/start_episode");
};

end_episode = function(ev){
    reason = undefined;
    request_get("{{url_prefix}}/task/end_episode?reward="+ev.reward+"&reason="+reason);
};
