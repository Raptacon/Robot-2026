/**
 * Field measurement point manager.
 *
 * Place labeled points on the field or around the robot, with
 * coordinates in field space. Points persist via server API.
 */

import * as THREE from 'three';

const POINT_RADIUS = 0.05;
const POINT_COLOR = 0x00ffaa;
const POINT_SELECTED_COLOR = 0xffaa00;

export class PointManager {
  constructor(scene) {
    this.scene = scene;
    this.points = [];           // [{ id, name, position: Vector3, mesh, label, selected }]
    this._nextId = 1;
    this.selectedPoint = null;
    this.onSelect = null;       // callback(point | null)
    this.onChange = null;        // callback() — called when points added/removed/moved
    this._addMode = false;      // true when waiting for click to place
    this.onAddModeChange = null; // callback(active)
  }

  // ── Add mode ──────────────────────────────────────────────────────

  enterAddMode() {
    this._addMode = true;
    if (this.onAddModeChange) this.onAddModeChange(true);
  }

  exitAddMode() {
    this._addMode = false;
    if (this.onAddModeChange) this.onAddModeChange(false);
  }

  get isAddMode() { return this._addMode; }

  // ── Point CRUD ────────────────────────────────────────────────────

  addPoint(position, name = null) {
    const id = this._nextId++;
    const ptName = name || `Point ${id}`;

    // Sphere mesh
    const geo = new THREE.SphereGeometry(POINT_RADIUS, 12, 12);
    const mat = new THREE.MeshBasicMaterial({
      color: POINT_COLOR, depthTest: false, transparent: true, opacity: 0.9,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.copy(position);
    mesh.renderOrder = 998;
    mesh.userData = { pointId: id };
    this.scene.add(mesh);

    // Label sprite
    const label = this._makeLabel(ptName, id);
    label.position.copy(position);
    label.position.z += POINT_RADIUS * 2.5;
    this.scene.add(label);

    // Vertical line from ground to point
    const lineGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(position.x, position.y, 0),
      new THREE.Vector3(position.x, position.y, position.z),
    ]);
    const line = new THREE.Line(lineGeo, new THREE.LineBasicMaterial({
      color: POINT_COLOR, transparent: true, opacity: 0.5,
    }));
    line.renderOrder = 997;
    this.scene.add(line);

    const point = { id, name: ptName, position: position.clone(), mesh, label, line, selected: false };
    this.points.push(point);

    if (this.onChange) this.onChange();
    return point;
  }

  removePoint(id) {
    const idx = this.points.findIndex(p => p.id === id);
    if (idx < 0) return;
    const pt = this.points[idx];
    this.scene.remove(pt.mesh);
    this.scene.remove(pt.label);
    this.scene.remove(pt.line);
    pt.mesh.geometry.dispose();
    pt.mesh.material.dispose();
    if (this.selectedPoint === pt) {
      this.selectedPoint = null;
      if (this.onSelect) this.onSelect(null);
    }
    this.points.splice(idx, 1);
    if (this.onChange) this.onChange();
  }

  movePoint(id, newPos) {
    const pt = this.points.find(p => p.id === id);
    if (!pt) return;
    pt.position.copy(newPos);
    pt.mesh.position.copy(newPos);
    pt.label.position.copy(newPos);
    pt.label.position.z += POINT_RADIUS * 2.5;
    // Update vertical line
    const positions = pt.line.geometry.attributes.position;
    positions.setXYZ(0, newPos.x, newPos.y, 0);
    positions.setXYZ(1, newPos.x, newPos.y, newPos.z);
    positions.needsUpdate = true;
    if (this.onChange) this.onChange();
  }

  setPointZ(id, z) {
    const pt = this.points.find(p => p.id === id);
    if (!pt) return;
    this.movePoint(id, new THREE.Vector3(pt.position.x, pt.position.y, z));
  }

  renamePoint(id, name) {
    const pt = this.points.find(p => p.id === id);
    if (!pt) return;
    pt.name = name;
    // Rebuild label
    this.scene.remove(pt.label);
    pt.label = this._makeLabel(name, id);
    pt.label.position.copy(pt.position);
    pt.label.position.z += POINT_RADIUS * 2.5;
    this.scene.add(pt.label);
    if (this.onChange) this.onChange();
  }

  // ── Selection ─────────────────────────────────────────────────────

  selectPoint(id) {
    // Deselect previous
    if (this.selectedPoint) {
      this.selectedPoint.mesh.material.color.setHex(POINT_COLOR);
      this.selectedPoint.selected = false;
    }
    const pt = id != null ? this.points.find(p => p.id === id) : null;
    if (pt) {
      pt.mesh.material.color.setHex(POINT_SELECTED_COLOR);
      pt.selected = true;
      this.selectedPoint = pt;
    } else {
      this.selectedPoint = null;
    }
    if (this.onSelect) this.onSelect(pt);
  }

  handleClick(raycaster) {
    if (this.points.length === 0) return null;
    const meshes = this.points.map(p => p.mesh);
    const hits = raycaster.intersectObjects(meshes, false);
    if (hits.length > 0) {
      const id = hits[0].object.userData.pointId;
      this.selectPoint(id);
      return this.selectedPoint;
    }
    return null;
  }

  // ── Persistence ───────────────────────────────────────────────────

  async savePoints(setName = 'default') {
    const data = {
      name: setName,
      points: this.points.map(p => ({
        id: p.id,
        name: p.name,
        x: Math.round(p.position.x * 10000) / 10000,
        y: Math.round(p.position.y * 10000) / 10000,
        z: Math.round(p.position.z * 10000) / 10000,
      })),
    };
    await fetch(`/api/points?set=${encodeURIComponent(setName)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    console.log(`[Points] Saved "${setName}" (${data.points.length} points)`);
  }

  async loadPoints(setName = 'default') {
    const res = await fetch(`/api/points?set=${encodeURIComponent(setName)}`);
    const data = await res.json();
    // Clear existing
    while (this.points.length > 0) {
      this.removePoint(this.points[0].id);
    }
    // Add loaded points
    if (data.points) {
      for (const p of data.points) {
        const pt = this.addPoint(
          new THREE.Vector3(p.x, p.y, p.z),
          p.name
        );
        pt.id = p.id;
        pt.mesh.userData.pointId = p.id;
        if (p.id >= this._nextId) this._nextId = p.id + 1;
      }
    }
    console.log(`[Points] Loaded "${setName}" (${this.points.length} points)`);
  }

  async listPointSets() {
    const res = await fetch('/api/points/list');
    return res.json();
  }

  // ── Helpers ───────────────────────────────────────────────────────

  _makeLabel(text, id) {
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, 256, 64);
    ctx.fillStyle = '#00ffaa';
    ctx.font = 'bold 28px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(text, 128, 38);
    const tex = new THREE.CanvasTexture(canvas);
    const mat = new THREE.SpriteMaterial({ map: tex, depthTest: false });
    const sprite = new THREE.Sprite(mat);
    sprite.scale.set(0.3, 0.075, 1);
    sprite.renderOrder = 999;
    sprite.userData = { pointId: id };
    return sprite;
  }

  clearAll() {
    while (this.points.length > 0) {
      this.removePoint(this.points[0].id);
    }
    this.selectedPoint = null;
    if (this.onChange) this.onChange();
  }
}
