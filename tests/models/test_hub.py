from nadin.models.hub import User, UserRoles


def test_set_initiative_project(app):
    user = User.query.filter_by(role=UserRoles.initiative).first()
    user.set_initiative_project()
    # assert len(user.projects) == 1
    # assert user.projects[0].name == user.name
    # assert user.projects[0].email == user.email
