import re, ast
from io import BytesIO
from typing import Optional

import LaylaRobot.modules.sql.notes_sql as sql
from LaylaRobot import LOGGER, JOIN_LOGGER, SUPPORT_CHAT, dispatcher, DRAGONS
from LaylaRobot.modules.disable import DisableAbleCommandHandler
from LaylaRobot.modules.helper_funcs.chat_status import user_admin, connection_status
from LaylaRobot.modules.helper_funcs.misc import (build_keyboard,
                                                    revert_buttons)
from LaylaRobot.modules.helper_funcs.msg_types import get_note_type
from LaylaRobot.modules.helper_funcs.string_handling import escape_invalid_curly_brackets
from telegram import (MAX_MESSAGE_LENGTH, InlineKeyboardMarkup, Message,
                      ParseMode, Update, InlineKeyboardButton)
from telegram.error import BadRequest
from telegram.utils.helpers import escape_markdown, mention_markdown
from telegram.ext import (CallbackContext, CommandHandler, CallbackQueryHandler,
                          Filters, MessageHandler)
from telegram.ext.dispatcher import run_async

FILE_MATCHER = re.compile(r"^###file_id(!photo)?###:(.*?)(?:\s|$)")
STICKER_MATCHER = re.compile(r"^###sticker(!photo)?###:")
BUTTON_MATCHER = re.compile(r"^###button(!photo)?###:(.*?)(?:\s|$)")
MYFILE_MATCHER = re.compile(r"^###file(!photo)?###:")
MYPHOTO_MATCHER = re.compile(r"^###photo(!photo)?###:")
MYAUDIO_MATCHER = re.compile(r"^###audio(!photo)?###:")
MYVOICE_MATCHER = re.compile(r"^###voice(!photo)?###:")
MYVIDEO_MATCHER = re.compile(r"^###video(!photo)?###:")
MYVIDEONOTE_MATCHER = re.compile(r"^###video_note(!photo)?###:")

ENUM_FUNC_MAP = {
    sql.Types.TEXT.value: dispatcher.bot.send_message,
    sql.Types.BUTTON_TEXT.value: dispatcher.bot.send_message,
    sql.Types.STICKER.value: dispatcher.bot.send_sticker,
    sql.Types.DOCUMENT.value: dispatcher.bot.send_document,
    sql.Types.PHOTO.value: dispatcher.bot.send_photo,
    sql.Types.AUDIO.value: dispatcher.bot.send_audio,
    sql.Types.VOICE.value: dispatcher.bot.send_voice,
    sql.Types.VIDEO.value: dispatcher.bot.send_video
}


# Do not async
@connection_status
def get(update, context, notename, show_none=True, no_format=False):
    bot = context.bot
    chat_id = update.effective_chat.id
    note = sql.get_note(chat_id, notename)
    message = update.effective_message  # type: Optional[Message]

    if note:
        # If we're replying to a message, reply to that message (unless it's an error)
        if message.reply_to_message:
            reply_id = message.reply_to_message.message_id
        else:
            reply_id = message.message_id

        if note.is_reply:
            if JOIN_LOGGER:
                try:
                    bot.forward_message(
                        chat_id=chat_id,
                        from_chat_id=JOIN_LOGGER,
                        message_id=note.value)
                except BadRequest as excp:
                    if excp.message == "G??nd??rm?? mesaj?? tap??lmad??":
                        message.reply_text(
                            "Bu mesaj itirilmi?? kimi g??r??n??r - onu sil??c??m "
                            "qeydl??r siyah??n??zdan.")
                        sql.rm_note(chat_id, notename)
                    else:
                        raise
            else:
                try:
                    bot.forward_message(
                        chat_id=chat_id,
                        from_chat_id=chat_id,
                        message_id=note.value)
                except BadRequest as excp:
                    if excp.message == "G??nd??rm?? mesaj?? tap??lmad??":
                        message.reply_text(
                            "Dey??s??n bu qeydin orijinal g??nd??ricisi silindi"
                            "mesajlar?? - ba??????lay??n! Bot administratorunuzu a istifad?? etm??y?? ba??lamaq ??????n al??n "
                            "Bunun qar????s??n?? almaq ??????n mesaj at??n. Bu qeydi ????xaraca??am "
                            "qeyd etdiyiniz qeydl??r.")
                        sql.rm_note(chat_id, notename)
                    else:
                        raise
        else:
            VALID_NOTE_FORMATTERS = [
                'first', 'last', 'fullname', 'username', 'id', 'chatname',
                'mention'
            ]
            valid_format = escape_invalid_curly_brackets(
                note.value, VALID_NOTE_FORMATTERS)
            if valid_format:
                text = valid_format.format(
                    first=escape_markdown(message.from_user.first_name),
                    last=escape_markdown(message.from_user.last_name or
                                         message.from_user.first_name),
                    fullname=escape_markdown(
                        " ".join([
                            message.from_user.first_name, message.from_user
                            .last_name
                        ] if message.from_user.last_name else
                                 [message.from_user.first_name])),
                    username="@" + message.from_user.username
                    if message.from_user.username else mention_markdown(
                        message.from_user.id, message.from_user.first_name),
                    mention=mention_markdown(message.from_user.id,
                                             message.from_user.first_name),
                    chatname=escape_markdown(
                        message.chat.title if message.chat.type != "private"
                        else message.from_user.first_name),
                    id=message.from_user.id)
            else:
                text = ""

            keyb = []
            parseMode = ParseMode.MARKDOWN
            buttons = sql.get_buttons(chat_id, notename)
            if no_format:
                parseMode = None
                text += revert_buttons(buttons)
            else:
                keyb = build_keyboard(buttons)

            keyboard = InlineKeyboardMarkup(keyb)

            try:
                if note.msgtype in (sql.Types.BUTTON_TEXT, sql.Types.TEXT):
                    bot.send_message(
                        chat_id,
                        text,
                        reply_to_message_id=reply_id,
                        parse_mode=parseMode,
                        disable_web_page_preview=True,
                        reply_markup=keyboard)
                else:
                    ENUM_FUNC_MAP[note.msgtype](
                        chat_id,
                        note.file,
                        caption=text,
                        reply_to_message_id=reply_id,
                        parse_mode=parseMode,
                        disable_web_page_preview=True,
                        reply_markup=keyboard)

            except BadRequest as excp:
                if excp.message == "Entity_mention_user_invalid":
                    message.reply_text(
                        "Dey??s??n ??vv??ll??r g??rm??diyim birinin ad??n?? ????km??y?? ??al????d??n. ??g??r h??qiq??t??n "
                        "onlardan b??hs etm??k ist??yir??m, mesajlar??ndan birini m??n?? ??atd??r??n, bacaraca??am "
                        "onlar?? etiketl??m??k ??????n!")
                elif FILE_MATCHER.match(note.value):
                    message.reply_text(
                        "Bu qeyd ba??qa bir botdan s??hv??n g??tirilmi?? bir fayl idi - istifad?? ed?? bilmir??m"
                        "??g??r h??qiq??t??n ehtiyac??n??z varsa, onu yenid??n saxlamal??s??n??z."
                        "bu vaxt qeydl??r siyah??n??zdan sil??c??m.")
                    sql.rm_note(chat_id, notename)
                else:
                    message.reply_text(
                        "Bu qeyd s??hv bi??iml??ndiyind??n g??nd??ril?? bilm??di. Soru?? "
                        f"@{SUPPORT_CHAT} n??yi anlaya bilmirs??ns??!")
                    LOGGER.exception("Could not parse message #%s in chat %s",
                                     notename, str(chat_id))
                    LOGGER.warning("Message was: %s", str(note.value))
        return
    elif show_none:
        message.reply_text("Bu qeyd yoxdur")


@run_async
@connection_status
def cmd_get(update: Update, context: CallbackContext):
    bot, args = context.bot, context.args
    if len(args) >= 2 and args[1].lower() == "noformat":
        get(update, context, args[0].lower(), show_none=True, no_format=True)
    elif len(args) >= 1:
        get(update, context, args[0].lower(), show_none=True)
    else:
        update.effective_message.reply_text("Rekt al??n")


@run_async
@connection_status
def hash_get(update: Update, context: CallbackContext):
    message = update.effective_message.text
    fst_word = message.split()[0]
    no_hash = fst_word[1:].lower()
    get(update, context, no_hash, show_none=False)


@run_async
@connection_status
def slash_get(update: Update, context: CallbackContext):
    message, chat_id = update.effective_message.text, update.effective_chat.id
    no_slash = message[1:]
    note_list = sql.get_all_chat_notes(chat_id)

    try:
        noteid = note_list[int(no_slash) - 1]
        note_name = str(noteid).strip(">").split()[1]
        get(update, context, note_name, show_none=False)
    except IndexError:
        update.effective_message.reply_text("S??hv Qeyd ID ????")


@run_async
@user_admin
@connection_status
def save(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    msg = update.effective_message  # type: Optional[Message]

    note_name, text, data_type, content, buttons = get_note_type(msg)
    note_name = note_name.lower()
    if data_type is None:
        msg.reply_text("Dostum, he?? bir qeyd yoxdur")
        return

    sql.add_note_to_db(
        chat_id, note_name, text, data_type, buttons=buttons, file=content)

    msg.reply_text(
        f"Yes! ??lav?? edildi `{note_name}`.\nAl??n /get `{note_name}`, or `#{note_name}`",
        parse_mode=ParseMode.MARKDOWN)

    if msg.reply_to_message and msg.reply_to_message.from_user.is_bot:
        if text:
            msg.reply_text(
                "Bir mesaj?? botdan saxlama??a ??al????d??????n??za b??nz??yir.T????ss??fki, "
                "botlar bot mesajlar??n?? ??t??r?? bilmir, ona g??r?? d?? d??qiq mesaj?? saxlaya bilmir??m  "
                "\nBacard??????m b??t??n m??tni saxlayacam, amma daha ??oxunu ist??yirs??ns?? etm??li olursan "
                "mesaj?? ??z??n??z y??nl??ndirin v?? sonra qeyd edin.")
        else:
            msg.reply_text(
                "Botlar telegramla passif olur v?? botlar??n i??ini ????tinl????dirir "
                "dig??r botlarla qar????l??ql?? ??laq??d?? oldu??um ??????n bu mesaj?? saxlaya bilmir??m "
                "ad??t??n ist??diyim kimi - onu ??t??rm??y?? "
                "sonra bu yeni mesaj?? yadda saxlama??a fikir vermirsinizmi? T??????kk??rl??r! ")
        return


@run_async
@user_admin
@connection_status
def clear(update: Update, context: CallbackContext):
    args = context.args
    chat_id = update.effective_chat.id
    if len(args) >= 1:
        notename = args[0].lower()

        if sql.rm_note(chat_id, notename):
            update.effective_message.reply_text("Qeyd u??urla silindi.")
        else:
            update.effective_message.reply_text(
                "Bu m??nim veril??nl??r bazamda olan bir qeyd deyil!")


@run_async
def clearall(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user
    member = chat.get_member(user.id)
    if member.status != "creator" and user.id not in DRAGONS:
        update.effective_message.reply_text(
            "Yaln??z s??hb??t sahibi bir anda b??t??n qeydl??ri sil?? bil??r.")
    else:
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                text="B??t??n qeydl??ri silin", callback_data="notes_rmall")
        ], [InlineKeyboardButton(text="Cancel", callback_data="notes_cancel")]])
        update.effective_message.reply_text(
            f"B??T??N qeydl??ri silm??k ist??diyiniz?? ??minsiniz{chat.title}? Bu ??m??liyyat geri qaytar??la bilm??z.",
            reply_markup=buttons,
            parse_mode=ParseMode.MARKDOWN)


@run_async
def clearall_btn(update: Update, context: CallbackContext):
    query = update.callback_query
    chat = update.effective_chat
    message = update.effective_message
    member = chat.get_member(query.from_user.id)
    if query.data == 'notes_rmall':
        if member.status == "creator" or query.from_user.id in DRAGONS:
            note_list = sql.get_all_chat_notes(chat.id)
            try:
                for notename in note_list:
                    note = notename.name.lower()
                    sql.rm_note(chat.id, note)
                message.edit_text("B??t??n qeydl??r silindi.")
            except BadRequest:
                return

        if member.status == "administrator":
            query.answer("Bunu yaln??z s??hb??t sahibi ed?? bil??r.")

        if member.status == "member":
            query.answer("Bunu etm??k ??????n admin olmal??s??n??z.")
    elif query.data == 'notes_cancel':
        if member.status == "creator" or query.from_user.id in DRAGONS:
            message.edit_text("B??t??n qeydl??rin silinm??si l????v edildi.")
            return
        if member.status == "administrator":
            query.answer("Bunu yaln??z s??hb??t sahibi ed?? bil??r.")
        if member.status == "member":
            query.answer("Bunu etm??k ??????n admin olmal??s??n??z.")


@run_async
@connection_status
def list_notes(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    note_list = sql.get_all_chat_notes(chat_id)
    notes = len(note_list) + 1
    msg = "T??r??find??n qeyd al??n `/notenumber` v?? ya `#notename` \n\n  *ID*    *Qeyd* \n"
    for note_id, note in zip(range(1, notes), note_list):
        if note_id < 10:
            note_name = f"`{note_id:2}.`  `#{(note.name.lower())}`\n"
        else:
            note_name = f"`{note_id}.`  `#{(note.name.lower())}`\n"
        if len(msg) + len(note_name) > MAX_MESSAGE_LENGTH:
            update.effective_message.reply_text(
                msg, parse_mode=ParseMode.MARKDOWN)
            msg = ""
        msg += note_name

    if not note_list:
        update.effective_message.reply_text("Bu s??hb??td?? qeyd yoxdur!")

    elif len(msg) != 0:
        update.effective_message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


def __import_data__(chat_id, data):
    failures = []
    for notename, notedata in data.get("extra", {}).items():
        match = FILE_MATCHER.match(notedata)
        matchsticker = STICKER_MATCHER.match(notedata)
        matchbtn = BUTTON_MATCHER.match(notedata)
        matchfile = MYFILE_MATCHER.match(notedata)
        matchphoto = MYPHOTO_MATCHER.match(notedata)
        matchaudio = MYAUDIO_MATCHER.match(notedata)
        matchvoice = MYVOICE_MATCHER.match(notedata)
        matchvideo = MYVIDEO_MATCHER.match(notedata)
        matchvn = MYVIDEONOTE_MATCHER.match(notedata)

        if match:
            failures.append(notename)
            notedata = notedata[match.end():].strip()
            if notedata:
                sql.add_note_to_db(chat_id, notename[1:], notedata,
                                   sql.Types.TEXT)
        elif matchsticker:
            content = notedata[matchsticker.end():].strip()
            if content:
                sql.add_note_to_db(
                    chat_id,
                    notename[1:],
                    notedata,
                    sql.Types.STICKER,
                    file=content)
        elif matchbtn:
            parse = notedata[matchbtn.end():].strip()
            notedata = parse.split("<###button###>")[0]
            buttons = parse.split("<###button###>")[1]
            buttons = ast.literal_eval(buttons)
            if buttons:
                sql.add_note_to_db(
                    chat_id,
                    notename[1:],
                    notedata,
                    sql.Types.BUTTON_TEXT,
                    buttons=buttons,
                )
        elif matchfile:
            file = notedata[matchfile.end():].strip()
            file = file.split("<###TYPESPLIT###>")
            notedata = file[1]
            content = file[0]
            if content:
                sql.add_note_to_db(
                    chat_id,
                    notename[1:],
                    notedata,
                    sql.Types.DOCUMENT,
                    file=content)
        elif matchphoto:
            photo = notedata[matchphoto.end():].strip()
            photo = photo.split("<###TYPESPLIT###>")
            notedata = photo[1]
            content = photo[0]
            if content:
                sql.add_note_to_db(
                    chat_id,
                    notename[1:],
                    notedata,
                    sql.Types.PHOTO,
                    file=content)
        elif matchaudio:
            audio = notedata[matchaudio.end():].strip()
            audio = audio.split("<###TYPESPLIT###>")
            notedata = audio[1]
            content = audio[0]
            if content:
                sql.add_note_to_db(
                    chat_id,
                    notename[1:],
                    notedata,
                    sql.Types.AUDIO,
                    file=content)
        elif matchvoice:
            voice = notedata[matchvoice.end():].strip()
            voice = voice.split("<###TYPESPLIT###>")
            notedata = voice[1]
            content = voice[0]
            if content:
                sql.add_note_to_db(
                    chat_id,
                    notename[1:],
                    notedata,
                    sql.Types.VOICE,
                    file=content)
        elif matchvideo:
            video = notedata[matchvideo.end():].strip()
            video = video.split("<###TYPESPLIT###>")
            notedata = video[1]
            content = video[0]
            if content:
                sql.add_note_to_db(
                    chat_id,
                    notename[1:],
                    notedata,
                    sql.Types.VIDEO,
                    file=content)
        elif matchvn:
            video_note = notedata[matchvn.end():].strip()
            video_note = video_note.split("<###TYPESPLIT###>")
            notedata = video_note[1]
            content = video_note[0]
            if content:
                sql.add_note_to_db(
                    chat_id,
                    notename[1:],
                    notedata,
                    sql.Types.VIDEO_NOTE,
                    file=content)
        else:
            sql.add_note_to_db(chat_id, notename[1:], notedata, sql.Types.TEXT)

    if failures:
        with BytesIO(str.encode("\n".join(failures))) as output:
            output.name = "failed_imports.txt"
            dispatcher.bot.send_document(
                chat_id,
                document=output,
                filename="failed_imports.txt",
                caption="Bu fayllar / ????kill??r m??n????li oldu??u ??????n idxal edilm??di "
                "ba??qa bir botdan. Bu telegram API m??hdudla??d??rmas??d??r v?? ed?? bilm??z "
                "qar????s??n?? al??m??b. Narahat????l????a g??r?? ??zr ist??yirik!",
            )


def __stats__():
    return f"??? {sql.num_notes()} notes, across {sql.num_chats()} chats."


def __migrate__(old_chat_id, new_chat_id):
    sql.migrate_chat(old_chat_id, new_chat_id)


def __chat_settings__(chat_id, user_id):
    notes = sql.get_all_chat_notes(chat_id)
    return f"Bu s??hb??td?? qeydl??r `{len(notes)}` var."


__help__ = """
 ??? `/get <qeydad??>`*:* bu ad?? il?? cavab al??n
 ??? `#<notename>`*:* eyni il?? /get
 ??? `/notes` v??ya `/saved`*:* bu s??hb??td??ki b??t??n qeydl??ri qeyd edin
 ??? `/number` *:* Siyah??da h??min n??mr??nin qeydini ????k??c??kdir.
Bir qeydin m??zmununu he?? bir formatla??d??rmadan ??ld?? etm??k ist??yirsinizs??, istifad?? edin `/get <qeydad??> `.Bu cari \
bir qeyd yenil??n??rk??n faydal?? ola bil??r.

*Yaln??z Adminl??r:*
 ??? `/save <qeydad??> <cavab>`*:* qeyd edilmi?? m??lumatlar?? ad ad?? il?? qeyd kimi qeyd edir
Standart i??ar??l??nm?? sintaksisind??n istifad?? ed??r??k bir qeyd?? bir d??ym?? ??lav?? edil?? bil??r - ke??id yaln??z a il?? ??lav?? olunmal??d??r\
`buttonurl:` b??lm??, bel??dir:`[istediyinlink](buttonurl:misal.com)`. Yoxlay??n `/markdownhelp` daha ??ox m??lumat ??????n.
 ??? `/save <qeydad??>`*:* cavab mesaj??n?? ad ad?? il?? qeyd kimi qeyd edin
 ??? `/clear <qeydad??>`*:* qeyd silin
 ??? `/removeallnotes`*:* b??t??n qeydl??ri qrupdan ????xar??r
 *QEYD:* Qeyd adlar?? h??rfl??r?? h??ssasd??r v?? qeyd olunmadan ??vv??l avtomatik olaraq ki??ik h??rfl??r?? ??evrilirl??r.
 
"""

__mod_name__ = "????Qeydl??r"

GET_HANDLER = CommandHandler("get", cmd_get)
HASH_GET_HANDLER = MessageHandler(Filters.regex(r"^#[^\s]+"), hash_get)
SLASH_GET_HANDLER = MessageHandler(Filters.regex(r"^/\d+$"), slash_get)
SAVE_HANDLER = CommandHandler("save", save)
DELETE_HANDLER = CommandHandler("clear", clear)

LIST_HANDLER = DisableAbleCommandHandler(["notes", "saved"],
                                         list_notes,
                                         admin_ok=True)

CLEARALL = DisableAbleCommandHandler("removeallnotes", clearall)
CLEARALL_BTN = CallbackQueryHandler(clearall_btn, pattern=r"notes_.*")

dispatcher.add_handler(GET_HANDLER)
dispatcher.add_handler(SAVE_HANDLER)
dispatcher.add_handler(LIST_HANDLER)
dispatcher.add_handler(DELETE_HANDLER)
dispatcher.add_handler(HASH_GET_HANDLER)
dispatcher.add_handler(SLASH_GET_HANDLER)
dispatcher.add_handler(CLEARALL)
dispatcher.add_handler(CLEARALL_BTN)
