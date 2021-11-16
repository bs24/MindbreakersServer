$(document).ready(function() {
  var flashing = false,
  focused = true;
  var title = document.title;

  $('.sub_form').on('submit', formListener);

  window.addEventListener('focus', function() {
    focused = true;
    flashing = false;
  });
  window.addEventListener('blur', function() {
    focused = false;
  });

  /* flash the title if necessary */
  setInterval(function() {
    if (flashing && !focused) {
      if (document.title[0] == '[') {
        document.title = title;
      } else {
        document.title = '[' + title + '] - New Guesss';
      }
    } else {
      document.title = title;
    }
  }, 1000);

  var get_posts = function() {
    $.ajax({
      type: 'get',
      url: "/staff/queue/",
      data: {last_date: last_date, all: true, puzzle_id: puzzle_id, team_id: team_id},
      success: function (response) {
        var response = JSON.parse(response);
        messages = response.guess_list;
        if(messages.length > 0){
          for (var i = 0; i < messages.length; i++) {
            receiveMessage(messages[i]);
          };
          last_date = response.last_date;
        }
      },
      error: function (html) {
        console.log(html);
      }
    });
  }
  setInterval(get_posts, 10000);

  function formListener(e) {
    e.preventDefault();
    old_row = $(this).parent().parent();
    $.ajax({
      url : $(this).attr('action') || window.location.pathname,
      type: "POST",
      data: $(this).serialize(),
      success: function (response) {
        response = JSON.parse(response);
        old_row.replaceWith($(response.guess_list[0]));
        $('.sub_form').on('submit', formListener);
      },
      error: function (jXHR, textStatus, errorThrown) {
        console.log(jXHR);
      }
    });
  }

  function receiveMessage(guess) {
    guess = $(guess);
    pk = guess.data('id');
    if ($('tr[data-id=' + pk + ']').length == 0) {
      if(!guess.hasClass('correct')) {
        flashing = !focused;
      }
      guess.prependTo("#sub_table");
      if($('#sub_table tr').length >= 30){
        $('#sub_table tr:last').remove();
      }
    } else {
      $('tr[data-id=' + pk + ']').replaceWith(guess);
    }
    $('.sub_form').on('submit', formListener);
  }

  /* open a text box for submitting an email */
  $(document).delegate('.needs-response', 'click', function() {
    $(this).siblings('form').show();
    return false;
  });
  $(document).delegate('.canned-response', 'click', function() {
    $(this).siblings('form').submit();
    return false;
  });
});
