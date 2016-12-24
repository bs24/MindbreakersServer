jQuery(document).ready(function($) {
  last_date = '{{last_date}}';
  var get_posts = function() {
    $.ajax({
      type: 'get',
      url: "/ajax/submission",
      data: {last_date: last_date},
      success: function (response) {
        var messages = JSON.parse(response);
        if(messages.length > 0){
          for (var i = 0; i < messages.length-1; i++) {
            receiveMessage(messages[i]);
          };
          console.log(messages[messages.length-1]);
          last_date = messages[messages.length-1];
        }
      },
      error: function (html) {
        console.log(html);
      }
    });
  }
  setInterval(get_posts, 3000);


  $('#sub_form').on('submit', function(e) {
    e.preventDefault();
    $.ajax({
      url : $(this).attr('action') || window.location.pathname,
      type: "POST",
      data: $(this).serialize(),
      error: function (jXHR, textStatus, errorThrown) {
        console.log(jXHR.responseText);
        alert(errorThrown);
      },
      success: function (jXHR, textStatus, errorThrown) {
        console.log(jXHR);
      }
    });
    $('#id_answer').val('');
  }); 

  // receive a message though the websocket from the server
  function receiveMessage(submission) {
    if(submission.puzzle == "{{ puzzle.puzzle_id }}"){
      row = $("<tr data-id='" + submission['pk'] + "'> </tr>");
      col1 = $("<td> " + submission['time_str'] + " </td>");
      col2 = $("<td> " + submission['submission_text'] + " </td>");
      col3 = $("<td> " + submission['response_text'] + " </td>");
      row.append(col1,col2,col3);
      if ($('tr[data-id=' + submission['pk'] + ']').length == 0) {
        row.prependTo("#sub_table");
      } else {
        $('tr[data-id=' + submission['pk'] + ']').replaceWith(row);
      }
    }
  }
});