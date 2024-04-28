"""
`calculate` module
==================

The `calculate` module is used to run various functions outside the scope of the `analyze` module. 

Every function from this module returns an `openpile.compute.CalculateResult` object. 

"""

import pandas as pd
import numpy as np
import math as m

from openpile.core._model_build import get_all_properties

class CalculateResult:
    _values: tuple




def _pile_element_surface(pile, soil):
    """calculates outer and inner surface of pile elements.

    Parameters
    ----------
    model : openpile.construct.Model

    Returns
    -------
    np.ndarray
        outside surface
    np.ndarray
        inside surface
    """

    _, element_properties, _, _ = get_all_properties(pile, soil, None, 0.1)

    perimeter_outside = element_properties["Diameter [m]"].values * m.pi
    perimeter_inside = (
        element_properties["Diameter [m]"].values
        - 2 * element_properties["Wall thickness [m]"]
    ) * m.pi
    L = (
        element_properties["x_top [m]"].values
        - element_properties["x_bottom [m]"].values
    )

    return perimeter_outside * L, perimeter_inside * L


def _pile_inside_volume(pile, soil):
    """calculates the volume of the pile form the model object

    Parameters
    ----------
    model : openpile.construct.Model

    Returns
    -------
    np.ndarray
        inside volume of each element
    """

    _, element_properties, _, _ = get_all_properties(pile, soil, None, 0.1)

    area_inside = (
        (
            element_properties["Diameter [m]"].values
            - 2 * element_properties["Wall thickness [m]"]
        )
        ** 2
        * m.pi
        / 4
    )
    L = (
        element_properties["x_top [m]"].values
        - element_properties["x_bottom [m]"].values
    )

    return area_inside * L


def effective_pile_weight(pile, soil):
    """Calculates the pile weight in the model with consideration of buoyancy

    Parameters
    ----------
    model : openpile.construct.Model
        OpenPile Model object

    Returns
    -------
    float
        pile weight in kN

    Raises
    ------
    Exception
        if soil profile does not exist

    See also
    --------
    `openpile.construct.Pile.weight`
    """

    _, element_properties, _, _ = get_all_properties(pile, soil, None, 0.1)

    if soil is not None:
        submerged_element = element_properties["x_bottom [m]"].values < soil.water_line

        L = (
            element_properties["x_top [m]"].values
            - element_properties["x_bottom [m]"].values
        )
        V = L * element_properties["Area [m2]"].values
        W = np.zeros(shape=V.shape)
        W[submerged_element] = V[submerged_element] * (pile.material.unitweight - 10)
        W[~submerged_element] = V[~submerged_element] * (pile.material.unitweight)

        return W.sum()

    else:
        raise Exception(
            "Model must be linked to a soil profile, use `openpile.construct.Pile.weight instead.`"
        )

def isplugged(pile,soil, method:str, kind:str="compression") -> bool:
    """_summary_

    Parameters
    ----------
    model : _type_
        _description_
    method : str
        _description_, should be one of ("API-87","ICP-05")
    kind : str, optional
        _description_, by default "compression"

    Returns
    -------
    bool
        _description_

    Raises
    ------
    Exception
        _description_
    """
    
    if method == "API-87":
        if kind == "compression":
            answer = unit_end_bearing(pile,soil)*(pile.tip_footprint - pile.tip_area) < shaft_resistance(pile,soil, outer_shaft=False, inner_shaft=True) - entrapped_soil_weight(pile,soil)
        elif kind == "tension":
            answer = entrapped_soil_weight(pile,soil) < shaft_resistance(pile,soil, outer_shaft=False, inner_shaft=True) 
    elif method == "ICP-05":
        pile_tip_criterion = m.sqrt(4 * pile.tip_footprint / m.pi)
        answer = True if pile_tip_criterion < 1.4 else False
    else:
        raise Exception("Method not implemented")
    
    return answer


def compressioncapacity(pile,soil):

    if isplugged(pile,soil, kind="compression"):
        Q = shaft_resistance(pile,soil, outer_shaft=True, inner_shaft=False) 
        + unit_end_bearing(pile,soil) * pile.tip_footprint - entrapped_soil_weight(pile,soil)
    else:
        Q = shaft_resistance(pile,soil, outer_shaft=True, inner_shaft=True) 
        + unit_end_bearing(pile,soil) * pile.tip_area
    
    return Q

def tensilecapacity(pile,soil):

    if isplugged(pile,soil, kind="tension"):
        Q = shaft_resistance(pile,soil, outer_shaft=True, inner_shaft=False) + entrapped_soil_weight(pile,soil)
    else:
        Q = shaft_resistance(pile,soil, outer_shaft=True, inner_shaft=True)

    return Q



def unit_end_bearing(
    pile,soil,
) -> float:

    soil_properties, _, _, _ = get_all_properties(pile, soil, None, 0.1)

    for layer in soil.layers:
        if layer.axial_model is None:
            q = 0.0
        else:
            # check if pile tip is within layer
            if (
                layer.top >= pile.bottom_elevation
                and layer.bottom <= pile.bottom_elevation
            ):
                # vertical effective stress at pile tip
                sig_v_tip = (soil_properties["sigma_v bottom [kPa]"].iloc[-1],)

                # Calculate unit tip resistance with effective area
                q = (
                    layer.axial_model.unit_tip_resistance(
                        sig=sig_v_tip,
                        depth_from_top_of_layer=(
                            soil.top_elevation - soil.bottom_elevation
                        ),
                        layer_height=(layer.top - layer.bottom),
                    )
                    * layer.axial_model.Q_multiplier
                )

    return q


def entrapped_soil_weight(pile,soil) -> float:
    """calculates total weight of soil inside the pile. (Unit: kN)

    Parameters
    ----------
    model : openpile.construct.Model
        OpenPile Model to assess

    Returns
    -------
    float
        value of entrapped total  weight of soil inside the pile in unit:kN
    """

    soil_properties, element_properties, _, _ = get_all_properties(pile, soil, None, 0.1)

    # weight water in kN/m3
    uw_water = 10

    # soil volume
    Vi = _pile_inside_volume(pile,soil)
    # element mid-point elevation
    elevation = 0.5 * (soil_properties["x_top [m]"] + soil_properties["x_bottom [m]"])
    # soil weight for each element where we have soil and pile
    elem_number = int(element_properties.shape[0])
    element_sw = np.zeros(elem_number)

    for layer in soil.layers:
        elements_for_layer = soil_properties.loc[
            (soil_properties["x_top [m]"] <= layer.top)
            & (soil_properties["x_bottom [m]"] >= layer.bottom)
        ].index

        # Set local layer parameters for each element of the layer
        for i in elements_for_layer:
            # Calculate inner soil weight
            element_sw[i] = (
                layer.weight * Vi[i]
                if elevation[i] <= soil.water_line
                else (layer.weight - uw_water) * Vi[i]
            )

    return element_sw.sum()


def shaft_resistance(
    pile,
    soil,
    outer_shaft:bool,
    inner_shaft:bool,
) -> float:
    """Calculates shaft resistance of the pile based on the axial models assigned to the SoilProfile layers. (Unit: kN)

    Parameters
    ----------
    model : openpile.construct.Model
        OpenPile Model to assess
    outer_shaft : bool, optional
        outer shaft resistance toggle switch, by default True
    inner_shaft : bool, optional
        inner shaft resistance toggle switch, by default True

    Returns
    -------
    float
        value of shaft resistance in unit:kN
    """

    soil_properties, element_properties, _, _ = get_all_properties(pile, soil, None, 0.1)
    elem_number = int(element_properties.shape[0])

    # pile element surfaces
    So, Si = _pile_element_surface(pile,soil)

    # get vertical effective stress
    sigveff = 0.5 * (
        soil_properties["sigma_v top [kPa]"] + soil_properties["sigma_v bottom [kPa]"]
    )

    # depth from ground
    depth_from_ground = (
        0.5 * (soil_properties["xg_top [m]"] + soil_properties["xg_bottom [m]"])
    ).abs()

    # shaft resistance for each element where we have soil and pile
    element_fs = np.zeros((2, elem_number))

    # loop over soil layers and assign shaft resistance
    for layer in soil.layers:
        elements_for_layer = soil_properties.loc[
            (soil_properties["x_top [m]"] <= layer.top)
            & (soil_properties["x_bottom [m]"] >= layer.bottom)
        ].index

        if layer.axial_model is None:
            pass
        else:
            # Set local layer parameters for each element of the layer
            for i in elements_for_layer:
                # depth from ground
                depth_from_ground = (
                    (soil_properties[["xg_top [m]", "xg_bottom [m]"]].iloc[i]).abs().mean()
                )

                # Calculate outer shaft resistance
                element_fs[0, i] = (
                    layer.axial_model.unit_shaft_friction(
                        sig=sigveff[i],
                        depth_from_top_of_layer=depth_from_ground,
                        layer_height=(layer.top - layer.bottom),
                    )
                    * layer.axial_model.unit_shaft_signature(So[i], Si[i])["out"]
                    * So[i]
                    * layer.axial_model.t_multiplier
                )
                # Calculate inner shaft resistance
                element_fs[1, i] = (
                    layer.axial_model.unit_shaft_friction(
                        sig=sigveff[i],
                        depth_from_top_of_layer=depth_from_ground,
                        layer_height=(layer.top - layer.bottom),
                    )
                    * layer.axial_model.unit_shaft_signature(So[i], Si[i])["in"]
                    * Si[i]
                    * layer.axial_model.t_multiplier
                )

    # overwrite shaft resistance when it is not called for 
    if outer_shaft is False:
        element_fs[0, :] = 0.0
    if inner_shaft is False:
        element_fs[1, :] = 0.0

    return element_fs.sum()
