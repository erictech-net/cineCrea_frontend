from datetime import datetime, time as dt_time, timezone

import streamlit as st
from supabase import create_client

# Doit être le premier appel Streamlit.
st.set_page_config(
    page_title="CineCréa — prototype académique -cinema ",
    page_icon="🎬",
    layout="wide",
)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_PUBLISHABLE_KEY = st.secrets["SUPABASE_PUBLISHABLE_KEY"]
SUPABASE_SECRET_KEY = st.secrets.get("SUPABASE_SECRET_KEY")


def new_client():
    return create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)


def new_admin_client():
    # Réservé aux opérations Auth côté serveur.
    if not SUPABASE_SECRET_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)


def save_session(session):
    st.session_state["access_token"] = session.access_token
    st.session_state["refresh_token"] = session.refresh_token


def clear_login():
    st.session_state.pop("access_token", None)
    st.session_state.pop("refresh_token", None)


def get_current_user(client):
    access_token = st.session_state.get("access_token")
    refresh_token = st.session_state.get("refresh_token")

    if not access_token or not refresh_token:
        return None

    try:
        response = client.auth.set_session(access_token, refresh_token)

        if response.session:
            save_session(response.session)

        return response.user
    except Exception:
        clear_login()
        return None


def get_role(user):
    if not user:
        return None

    metadata = getattr(user, "app_metadata", {}) or {}
    # Les comptes sans rôle spécial sont des clients.
    return metadata.get("role", "client")


def parse_datetime(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def local_datetime(value):
    return parse_datetime(value).astimezone().strftime("%d/%m/%Y à %H:%M")


def load_catalog(client):
    films = (
            client.table("films")
            .select("id,titre,genre,poster_url,description,note")
            .order("titre")
            .execute()
            .data
            or []
    )

    seances = (
            client.table("seances")
            .select("id,film_id,date_heure,prix")
            .order("date_heure")
            .execute()
            .data
            or []
    )

    return films, seances


def render_auth_sidebar(client, user):
    st.sidebar.title("Mon compte")

    if user:
        st.sidebar.write(f"Connecté : **{user.email}**")
        st.sidebar.write(f"Espace : `{get_role(user)}`")

        if st.sidebar.button("Se déconnecter", key="logout"):
            try:
                client.auth.sign_out()
            except Exception:
                pass
            clear_login()
            st.rerun()

        return

    with st.sidebar.expander("Se connecter", expanded=True):
        with st.form("login_form"):
            email = st.text_input("E-mail", key="login_email")
            password = st.text_input(
                "Mot de passe",
                type="password",
                key="login_password",
            )
            submit_login = st.form_submit_button(
                "Se connecter",
                type="primary",
            )

        if submit_login:
            try:
                response = client.auth.sign_in_with_password(
                    {"email": email, "password": password}
                )

                if response.session:
                    save_session(response.session)
                    st.rerun()
                else:
                    st.sidebar.error("La connexion n’a pas créé de session.")
            except Exception as exc:
                st.sidebar.error(f"Connexion impossible : {exc}")

    # Inscription publique, visible même sans cliquer sur Réserver.
    with st.sidebar.expander("Créer un compte client", expanded=True):
        with st.form("signup_form"):
            new_email = st.text_input("E-mail", key="signup_email")
            new_password = st.text_input(
                "Mot de passe (8 caractères minimum)",
                type="password",
                key="signup_password",
            )
            submit_signup = st.form_submit_button("Créer mon compte")

        if submit_signup:
            if len(new_password) < 8:
                st.sidebar.error(
                    "Le mot de passe doit contenir au moins 8 caractères."
                )
            else:
                try:
                    response = client.auth.sign_up(
                        {
                            "email": new_email,
                            "password": new_password,
                        }
                    )

                    if response.session:
                        save_session(response.session)
                        st.sidebar.success("Compte créé et connecté.")
                        st.rerun()
                    else:
                        st.sidebar.success(
                            "Compte créé. Confirme ton adresse e-mail si "
                            "Supabase le demande, puis connecte-toi ici."
                        )
                except Exception as exc:
                    st.sidebar.error(
                        f"Création du compte impossible : {exc}"
                    )


def ticket_from_rpc(data, seance_id, seance):
    if isinstance(data, list):
        ticket = data[0] if data else {}
    elif isinstance(data, dict):
        ticket = data
    else:
        ticket = {}

    ticket = dict(ticket)
    ticket.setdefault("reservation_id", ticket.get("id", "—"))
    ticket.setdefault("seance_id", int(seance_id))
    ticket.setdefault("total_price", seance.get("prix", "—"))
    ticket.setdefault("status", "confirmee")

    st.session_state["last_ticket"] = ticket


def render_ticket(ticket, films_by_id, seances_by_id):
    seance = seances_by_id.get(int(ticket["seance_id"]))
    film = films_by_id.get(int(seance["film_id"])) if seance else None

    title = film["titre"] if film else "Film"
    when = local_datetime(seance["date_heure"]) if seance else "—"
    reference = ticket["reservation_id"]
    price = ticket["total_price"]
    status = ticket["status"]

    st.success(f"Réservation confirmée — ticket nº {reference}")
    st.write(f"**{title}**")
    st.write(f"Séance : {when}")
    st.write(f"Prix : {price} €")
    st.write(f"Statut : {status}")
    st.caption("Paiement fictif — aucune somme n’a été prélevée.")

    receipt = (
        "TICKET DE CINÉMA — DÉMO ACADÉMIQUE\n"
        f"Référence : {reference}\n"
        f"Film : {title}\n"
        f"Séance : {when}\n"
        f"Prix affiché : {price} EUR\n"
        f"Statut : {status}\n"
        "Paiement fictif — aucune somme n’a été prélevée.\n"
    )

    st.download_button(
        "Télécharger le ticket",
        data=receipt,
        file_name=f"ticket-{reference}.txt",
        mime="text/plain",
        key=f"download-ticket-{reference}",
    )


def render_admin(client, admin_client):
    st.subheader("Espace administrateur")

    films = (
            client.table("films")
            .select("id,titre,genre,poster_url,description,note")
            .order("titre")
            .execute()
            .data
            or []
    )
    films_by_id = {int(f["id"]): f for f in films}

    # Création d'un film
    with st.expander("Ajouter un film"):
        with st.form("admin_add_film"):
            title = st.text_input("Titre")
            genre = st.text_input("Genre")
            poster_url = st.text_input("URL de l’affiche")
            description = st.text_area("Description")
            note = st.number_input(
                "Note sur 10",
                min_value=0.0,
                max_value=10.0,
                value=0.0,
                step=0.1,
            )
            add_film = st.form_submit_button("Ajouter le film")

        if add_film:
            try:
                client.table("films").insert(
                    {
                        "titre": title.strip(),
                        "genre": genre.strip() or None,
                        "poster_url": poster_url.strip() or None,
                        "description": description.strip() or None,
                        "note": note,
                    }
                ).execute()
                st.success("Film ajouté.")
                st.rerun()
            except Exception as exc:
                st.error(f"Ajout impossible : {exc}")

    # Modification et suppression d'un film
    with st.expander("Modifier ou supprimer un film"):
        if not films:
            st.info("Aucun film enregistré.")
        else:
            film_id = st.selectbox(
                "Film",
                list(films_by_id.keys()),
                format_func=lambda i: films_by_id[i]["titre"],
                key="admin_film_id",
            )
            film = films_by_id[film_id]

            with st.form(f"admin_edit_film_{film_id}"):
                title = st.text_input("Titre", value=film.get("titre") or "")
                genre = st.text_input("Genre", value=film.get("genre") or "")
                poster_url = st.text_input(
                    "URL de l’affiche",
                    value=film.get("poster_url") or "",
                )
                description = st.text_area(
                    "Description",
                    value=film.get("description") or "",
                )
                note = st.number_input(
                    "Note sur 10",
                    min_value=0.0,
                    max_value=10.0,
                    value=float(film.get("note") or 0),
                    step=0.1,
                    key=f"film-note-{film_id}",
                )
                update_film = st.form_submit_button("Enregistrer")

            if update_film:
                try:
                    client.table("films").update(
                        {
                            "titre": title.strip(),
                            "genre": genre.strip() or None,
                            "poster_url": poster_url.strip() or None,
                            "description": description.strip() or None,
                            "note": note,
                        }
                    ).eq("id", film_id).execute()
                    st.success("Film modifié.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Modification impossible : {exc}")

            confirm = st.checkbox(
                "Je confirme la suppression de ce film",
                key=f"confirm-film-delete-{film_id}",
            )
            if st.button(
                    "Supprimer le film",
                    disabled=not confirm,
                    key=f"delete-film-{film_id}",
            ):
                try:
                    client.table("films").delete().eq("id", film_id).execute()
                    st.success("Film supprimé.")
                    st.rerun()
                except Exception as exc:
                    st.error(
                        "Suppression impossible, peut-être parce que des "
                        f"séances sont liées à ce film. Détail : {exc}"
                    )

    # Séances
    seances = (
            client.table("seances")
            .select("id,film_id,date_heure,prix")
            .order("date_heure", desc=True)
            .execute()
            .data
            or []
    )
    seances_by_id = {int(s["id"]): s for s in seances}

    with st.expander("Ajouter une séance"):
        if not films:
            st.info("Ajoute un film avant de créer une séance.")
        else:
            with st.form("admin_add_seance"):
                film_id = st.selectbox(
                    "Film",
                    list(films_by_id.keys()),
                    format_func=lambda i: films_by_id[i]["titre"],
                )
                day = st.date_input("Date")
                hour = st.time_input("Heure", value=dt_time(19, 0))
                price = st.number_input(
                    "Prix (€)",
                    min_value=7.0,
                    max_value=15.0,
                    value=10.0,
                    step=0.5,
                )
                add_seance = st.form_submit_button("Ajouter la séance")

            if add_seance:
                try:
                    date_heure = datetime.combine(day, hour).astimezone()
                    client.table("seances").insert(
                        {
                            "film_id": film_id,
                            "date_heure": date_heure.isoformat(),
                            "prix": price,
                        }
                    ).execute()
                    st.success("Séance ajoutée.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Ajout de séance impossible : {exc}")

    with st.expander("Modifier ou supprimer une séance"):
        if not seances:
            st.info("Aucune séance enregistrée.")
        else:
            seance_id = st.selectbox(
                "Séance",
                list(seances_by_id.keys()),
                format_func=lambda i: (
                    f"{films_by_id.get(int(seances_by_id[i]['film_id']), {}).get('titre', 'Film')} — "
                    f"{local_datetime(seances_by_id[i]['date_heure'])}"
                ),
                key="admin_seance_id",
            )
            seance = seances_by_id[seance_id]

            with st.form(f"admin_edit_seance_{seance_id}"):
                film_ids = list(films_by_id.keys())
                old_film_id = int(seance["film_id"])
                film_index = (
                    film_ids.index(old_film_id)
                    if old_film_id in film_ids
                    else 0
                )
                new_film_id = st.selectbox(
                    "Film",
                    film_ids,
                    index=film_index,
                    format_func=lambda i: films_by_id[i]["titre"],
                )
                price = st.number_input(
                    "Prix (€)",
                    min_value=7.0,
                    max_value=15.0,
                    value=float(seance["prix"]),
                    step=0.5,
                    key=f"seance-price-{seance_id}",
                )
                update_seance = st.form_submit_button("Modifier la séance")

            if update_seance:
                try:
                    client.table("seances").update(
                        {"film_id": new_film_id, "prix": price}
                    ).eq("id", seance_id).execute()
                    st.success("Séance modifiée.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Modification impossible : {exc}")

            confirm = st.checkbox(
                "Je confirme la suppression de cette séance",
                key=f"confirm-seance-delete-{seance_id}",
            )
            if st.button(
                    "Supprimer la séance",
                    disabled=not confirm,
                    key=f"delete-seance-{seance_id}",
            ):
                try:
                    client.table("seances").delete().eq(
                        "id", seance_id
                    ).execute()
                    st.success("Séance supprimée.")
                    st.rerun()
                except Exception as exc:
                    st.error(
                        "Suppression impossible, peut-être parce que des "
                        f"réservations y sont liées. Détail : {exc}"
                    )

    # Création de comptes vendeur/admin
    with st.expander("Créer un compte vendeur ou admin"):
        if not admin_client:
            st.warning(
                "Ajoute SUPABASE_SECRET_KEY aux secrets du serveur pour "
                "activer cette fonction."
            )
        else:
            with st.form("admin_create_staff"):
                staff_email = st.text_input("E-mail du compte")
                staff_password = st.text_input(
                    "Mot de passe initial",
                    type="password",
                )
                staff_role = st.selectbox("Rôle", ["vendeur", "admin"])
                create_staff = st.form_submit_button("Créer le compte")

            if create_staff:
                if len(staff_password) < 8:
                    st.error("Le mot de passe doit faire au moins 8 caractères.")
                else:
                    try:
                        admin_client.auth.admin.create_user(
                            {
                                "email": staff_email.strip(),
                                "password": staff_password,
                                "email_confirm": True,
                                "app_metadata": {"role": staff_role},
                            }
                        )
                        st.success(
                            f"Compte {staff_role} créé. Transmets le mot "
                            "de passe initial de façon sécurisée."
                        )
                    except Exception as exc:
                        st.error(f"Création du compte impossible : {exc}")


client = new_client()
admin_client = new_admin_client()
user = get_current_user(client)
role = get_role(user)

st.title("🎬 Cinéma")
st.caption("Catalogue public — réserve une séance depuis l’affiche.")
st.warning(
    "Paiement fictif : aucune carte bancaire n’est demandée "
    "et aucune somme n’est prélevée."
)

render_auth_sidebar(client, user)

if user and role == "admin":
    render_admin(client, admin_client)

if user and role == "vendeur":
    st.subheader("Espace vendeur")
    st.write(f"Connecté : **{user.email}**")

    try:
        rows = (
                client.table("reservations")
                .select("id,client_name,total_price,status,created_at")
                .eq("created_by", user.id)
                .order("created_at", desc=True)
                .execute()
                .data
                or []
        )

        if not rows:
            st.info("Aucune réservation associée à ce compte vendeur.")
        else:
            for row in rows:
                st.write(
                    f"Réservation {row['id']} — "
                    f"{row['client_name']} — {row['total_price']} € — "
                    f"{row['status']}"
                )
    except Exception as exc:
        st.error(f"Chargement des réservations impossible : {exc}")

# Le catalogue est public : il est chargé même si personne n'est connecté.
try:
    films, all_seances = load_catalog(client)
except Exception as exc:
    st.error(
        "Impossible de charger le catalogue. Vérifie les permissions de "
        f"lecture publique sur films et seances. Détail : {exc}"
    )
    st.stop()

films_by_id = {int(film["id"]): film for film in films}
seances_by_id = {int(seance["id"]): seance for seance in all_seances}

now = datetime.now(timezone.utc)
future_by_film = {}

for seance in all_seances:
    try:
        if parse_datetime(seance["date_heure"]) > now:
            film_id = int(seance["film_id"])
            future_by_film.setdefault(film_id, []).append(seance)
    except (TypeError, ValueError):
        continue

st.subheader("Films à l’affiche")

if not films:
    st.info("Aucun film enregistré.")
else:
    for start in range(0, len(films), 3):
        columns = st.columns(3)

    for column, film in zip(columns, films[start: start + 3]):
        film_id = int(film["id"])

        with column:
            if film.get("poster_url"):
                st.image(
                    film["poster_url"],
                    use_container_width=True,
                )

            st.subheader(film["titre"])

            if film.get("genre"):
                st.write(f"Genre : {film['genre']}")
            if film.get("note") is not None:
                st.write(f"Note : {film['note']}/10")
            if film.get("description"):
                st.write(film["description"])

            film_seances = future_by_film.get(film_id, [])

            if film_seances:
                session_map = {
                    int(s["id"]): s for s in film_seances
                }
                selected_seance_id = st.selectbox(
                    "Choisir une séance",
                    list(session_map.keys()),
                    format_func=lambda sid: (
                        f"{local_datetime(session_map[sid]['date_heure'])}"
                        f" — {session_map[sid]['prix']} €"
                    ),
                    key=f"session-{film_id}",
                )
            else:
                selected_seance_id = None
                st.caption("Aucune séance future pour le moment.")

            # Ce bouton reste visible publiquement, même sans compte.
            if st.button(
                    "Réserver",
                    type="primary",
                    key=f"reserve-{film_id}",
                    use_container_width=True,
            ):
                if selected_seance_id is None:
                    st.warning(
                        "Aucune séance future n’est programmée pour "
                        "ce film. Un admin doit en ajouter une."
                    )
                else:
                    st.session_state["pending_seance_id"] = (
                        int(selected_seance_id)
                    )
                    st.rerun()

# Suite de réservation conservée après connexion ou création du compte.
pending_id = st.session_state.get("pending_seance_id")

if pending_id:
    pending_seance = seances_by_id.get(int(pending_id))

    st.divider()
    st.subheader("Réservation")

    if not pending_seance:
        st.warning("Cette séance n’est plus disponible.")
        st.session_state.pop("pending_seance_id", None)

    elif not user:
        st.info(
            "La séance est sélectionnée. Connecte-toi ou crée ton compte "
            "dans la barre latérale pour continuer."
        )

    elif role in ("admin", "vendeur"):
        st.info(
            "Connecte-toi avec un compte client pour effectuer une "
            "réservation client."
        )

    else:
        film = films_by_id.get(int(pending_seance["film_id"]), {})
        st.write(f"Film : **{film.get('titre', 'Film')}**")
        st.write(
            f"Séance : **{local_datetime(pending_seance['date_heure'])}**"
        )
        st.write(f"Prix fictif : **{pending_seance['prix']} €**")

        if st.button(
                "Confirmer la réservation — paiement fictif",
                type="primary",
                key="confirm-booking",
        ):
            try:
                result = (
                    client.rpc(
                        "reserver_seance",
                        {"p_seance_id": int(pending_id)},
                    )
                    .execute()
                    .data
                )

                ticket_from_rpc(result, int(pending_id), pending_seance)
                st.session_state.pop("pending_seance_id", None)
                st.rerun()
            except Exception as exc:
                st.error(
                    "Réservation impossible. Vérifie la fonction "
                    "`reserver_seance` et ses règles RLS. "
                    f"Détail : {exc}"
                )

ticket = st.session_state.get("last_ticket")
if ticket:
    st.divider()
    st.subheader("Mon ticket")
    render_ticket(ticket, films_by_id, seances_by_id)

st.divider()
st.caption(
    "Prototype académique — paiement fictif, aucune transaction réelle."
)
